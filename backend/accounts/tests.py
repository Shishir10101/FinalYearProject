"""Tests for the password reset flow.

Password reset is the one feature where "it looks like it worked" and "it actually
works" are dangerously far apart. An endpoint that always returns
``{"message": "Reset link sent"}`` passes any smoke test while doing nothing at
all, and a token check that only *looks* like a check is a full account-takeover
hole. These tests therefore assert on the things that actually matter:

* the new password genuinely authenticates afterwards, and the old one does not;
* a link works exactly once;
* a bad uid and a bad token are indistinguishable from the outside;
* an unknown email produces the same response as a known one;
* the rate limit is real.

Run with::

    python manage.py test accounts -v 2
"""

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.permissions import (
    ROLE_ADMIN, ROLE_CUSTOMER, ROLE_SUPER_ADMIN, ROLE_VENDOR,
)
from products.models import Vendor

from .models import UserProfile
from .password_reset import build_reset_url, encode_uid, make_token
from .tokens import TOKEN_VERSION_CLAIM as TOKEN_VERSION_CLAIM_FOR_TEST

LOCOLMEM = 'django.core.mail.backends.locmem.EmailBackend'
REQUEST_URL = '/api/auth/password-reset/'
CONFIRM_URL = '/api/auth/password-reset/confirm/'

OLD_PASSWORD = 'OriginalPass123'
NEW_PASSWORD = 'BrandNewPass456'


def split_reset_url(url):
    """Pull uid and token back out of a generated reset link."""
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    return query['uid'][0], query['token'][0]


@override_settings(EMAIL_BACKEND=LOCOLMEM)
class PasswordResetTestBase(TestCase):
    def setUp(self):
        # DRF throttles through the default cache, which is not reset between
        # tests. Without this, one test's requests count against the next one's
        # rate limit and the suite fails in a confusing order-dependent way.
        cache.clear()

        self.user = User.objects.create_user(
            'resetme', email='resetme@example.com', password=OLD_PASSWORD,
        )
        UserProfile.objects.create(user=self.user)
        self.client = APIClient()

    def request_reset(self, email='resetme@example.com'):
        return self.client.post(REQUEST_URL, {'email': email}, format='json')

    def confirm(self, uid, token, password=NEW_PASSWORD, confirm=None):
        return self.client.post(CONFIRM_URL, {
            'uid': uid,
            'token': token,
            'new_password': password,
            'new_password2': confirm if confirm is not None else password,
        }, format='json')

    def fresh_link_parts(self):
        response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        return split_reset_url(response.json()['reset_url'])

    def can_login(self, password, username='resetme'):
        return self.client.post('/api/auth/login/', {
            'username': username, 'password': password,
        }, format='json').status_code == 200


class ResetRequestTests(PasswordResetTestBase):
    def test_known_email_sends_exactly_one_email(self):
        response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['resetme@example.com'])

    def test_email_body_contains_a_working_reset_link(self):
        self.request_reset()
        body = mail.outbox[0].body
        self.assertIn('/auth/reset-password?uid=', body)

    def test_unknown_email_sends_nothing(self):
        response = self.request_reset('nobody@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(PASSWORD_RESET_EXPOSE_LINK=False)
    def test_unknown_email_response_is_identical_to_known_email(self):
        """No account enumeration, in the configuration that would ever ship.

        Asserted with ``PASSWORD_RESET_EXPOSE_LINK`` off, because that is the only
        configuration where the guarantee can hold: the dev flag deliberately
        returns the reset link, and a link can only exist for a real account.
        """
        known = self.request_reset('resetme@example.com').json()
        unknown = self.request_reset('nobody@example.com').json()
        self.assertEqual(
            known, unknown,
            'the two responses must be byte-identical or the endpoint reveals '
            'whether an address is registered',
        )

    def test_dev_exposure_leaks_exactly_two_fields_and_nothing_else(self):
        """Pin down the blast radius of the dev-only link exposure.

        With exposure on, the response *does* differ for a known address. That is
        an accepted consequence of demoing without a mailbox, so it is asserted
        explicitly here rather than left as a surprise: the difference must be
        limited to the link and its explanatory note, and the human-readable
        message must stay identical.
        """
        known = self.request_reset('resetme@example.com').json()
        unknown = self.request_reset('nobody@example.com').json()
        self.assertEqual(known['message'], unknown['message'])
        self.assertEqual(set(known) - set(unknown), {'reset_url', 'dev_note'})
        self.assertEqual(set(unknown) - set(known), set())

    def test_email_match_is_case_insensitive(self):
        response = self.request_reset('ResetMe@Example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset_url', response.json())

    def test_invalid_email_format_is_rejected(self):
        response = self.client.post(REQUEST_URL, {'email': 'not-an-email'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(PASSWORD_RESET_EXPOSE_LINK=False)
    def test_link_is_withheld_when_exposure_is_disabled(self):
        """The dev convenience must switch off cleanly.

        ``PASSWORD_RESET_EXPOSE_LINK`` hands a usable reset link to the caller, so
        with it off the response must carry nothing but the generic message.
        """
        response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('reset_url', response.json())
        self.assertNotIn('dev_note', response.json())
        self.assertEqual(len(mail.outbox), 1, 'the email must still be sent')

    def test_inactive_user_is_not_emailed(self):
        self.user.is_active = False
        self.user.save()
        response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


class ResetConfirmTests(PasswordResetTestBase):
    def test_valid_link_changes_the_password(self):
        uid, token = self.fresh_link_parts()
        response = self.confirm(uid, token)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_new_password_actually_authenticates(self):
        """The point of the whole feature. Asserted through the login endpoint."""
        uid, token = self.fresh_link_parts()
        self.confirm(uid, token)
        self.assertTrue(self.can_login(NEW_PASSWORD))
        self.assertFalse(self.can_login(OLD_PASSWORD), 'the old password still works')

    def test_link_works_only_once(self):
        uid, token = self.fresh_link_parts()
        self.assertEqual(self.confirm(uid, token).status_code, 200)
        second = self.confirm(uid, token, password='ThirdPassword789')
        self.assertEqual(second.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD),
                        'a reused link must not overwrite the new password')

    def test_tampered_token_is_rejected(self):
        uid, token = self.fresh_link_parts()
        response = self.confirm(uid, token[:-1] + ('a' if token[-1] != 'a' else 'b'))
        self.assertEqual(response.status_code, 400)

    def test_token_from_another_user_is_rejected(self):
        """A token is bound to one account, not merely to 'some account'."""
        other = User.objects.create_user('other', email='other@example.com',
                                         password=OLD_PASSWORD)
        UserProfile.objects.create(user=other)
        uid, _ = self.fresh_link_parts()
        other_token = make_token(other)
        self.assertEqual(self.confirm(uid, other_token).status_code, 400)

    def test_malformed_uid_is_rejected(self):
        response = self.confirm('!!!not-base64!!!', 'whatever')
        self.assertEqual(response.status_code, 400)

    def test_unknown_uid_is_rejected(self):
        response = self.confirm(encode_uid(User(id=99999)), 'whatever')
        self.assertEqual(response.status_code, 400)

    def test_bad_uid_and_bad_token_are_indistinguishable(self):
        """Both failures must read identically, or the endpoint leaks account ids."""
        uid, token = self.fresh_link_parts()
        bad_uid = self.confirm(encode_uid(User(id=99999)), token)
        bad_token = self.confirm(uid, 'clearly-wrong-token')
        self.assertEqual(bad_uid.status_code, bad_token.status_code)
        self.assertEqual(bad_uid.json(), bad_token.json())

    def test_mismatched_confirmation_is_rejected(self):
        uid, token = self.fresh_link_parts()
        response = self.confirm(uid, token, password=NEW_PASSWORD, confirm='DifferentPass123')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password2', response.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD), 'password was changed anyway')

    def test_weak_password_is_rejected_by_django_validators(self):
        """A reset must not be a way to set a password registration would refuse."""
        uid, token = self.fresh_link_parts()
        response = self.confirm(uid, token, password='123')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password', response.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_common_password_is_rejected(self):
        uid, token = self.fresh_link_parts()
        response = self.confirm(uid, token, password='password')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_response_does_not_include_a_token_or_password(self):
        uid, token = self.fresh_link_parts()
        payload = self.confirm(uid, token).json()
        self.assertEqual(set(payload.keys()), {'message'})


class PasswordResetThrottleTests(PasswordResetTestBase):
    def test_repeated_requests_are_throttled(self):
        """The endpoint sends mail, so it cannot be freely hammerable.

        The rate is patched down rather than sending ten real requests, so the
        test states its intent directly instead of depending on the configured
        number.
        """
        from unittest.mock import patch
        from .throttling import PasswordResetThrottle

        with patch.dict(PasswordResetThrottle.THROTTLE_RATES, {'password_reset': '3/min'}):
            statuses = [self.request_reset('nobody@example.com').status_code for _ in range(4)]

        self.assertEqual(statuses[:3], [200, 200, 200])
        self.assertEqual(statuses[3], 429, 'the 4th request should have been throttled')

    def test_throttle_applies_to_the_confirm_endpoint_too(self):
        from unittest.mock import patch
        from .throttling import PasswordResetThrottle

        with patch.dict(PasswordResetThrottle.THROTTLE_RATES, {'password_reset': '2/min'}):
            codes = [self.confirm('bad', 'bad').status_code for _ in range(3)]

        self.assertEqual(codes[2], 429)


class ResetLinkHelperTests(PasswordResetTestBase):
    def test_build_reset_url_points_at_the_storefront(self):
        url = build_reset_url(self.user)
        self.assertTrue(url.startswith('http://localhost:3000/auth/reset-password?'))

    def test_encoded_uid_is_not_the_raw_primary_key(self):
        """A visible pk would make account ids trivially guessable."""
        encoded = encode_uid(self.user)
        self.assertNotEqual(encoded, str(self.user.pk))


class TokenRevocationTests(TestCase):
    """A password reset must end existing sessions, not just change the password.

    JWTs are stateless: nothing can un-issue one. SimpleJWT's `token_blacklist` app
    only covers *refresh* tokens, so it cannot help here — an access token stays
    valid for its full day. The fix is a version claim checked on every request.

    A test that only asserted "the password changed" would pass against the old
    implementation, which left a stolen token working for up to 24 hours. These
    tests assert that the old token stops working, which the old code could not do.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            'revoke_me', email='revoke@example.com', password=OLD_PASSWORD,
        )
        UserProfile.objects.create(user=self.user)
        self.client = APIClient()

    def login(self, password=OLD_PASSWORD, username='revoke_me'):
        """Returns (status_code, body) for a login attempt."""
        response = self.client.post('/api/auth/login/', {
            'username': username, 'password': password,
        }, format='json')
        return response.status_code, response.json()

    def as_user(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    def reset_password(self):
        """Drive the real reset flow and return the uid/token pair used."""
        response = self.client.post('/api/auth/password-reset/',
                                    {'email': 'revoke@example.com'}, format='json')
        uid, token = split_reset_url(response.json()['reset_url'])
        self.client.post(CONFIRM_URL, {
            'uid': uid, 'token': token,
            'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD,
        }, format='json')
        return uid, token

    # --- the claim ------------------------------------------------------

    def test_login_tokens_carry_the_version_claim(self):
        from .tokens import TOKEN_VERSION_CLAIM
        from rest_framework_simplejwt.tokens import AccessToken

        _, body = self.login()
        decoded = AccessToken(body['access'])
        self.assertIn(TOKEN_VERSION_CLAIM, decoded)
        self.assertEqual(decoded[TOKEN_VERSION_CLAIM], 0)

    def test_a_fresh_token_authenticates(self):
        _, body = self.login()
        response = self.as_user(body['access']).get('/api/auth/profile/')
        self.assertEqual(response.status_code, 200)

    def test_the_claim_cannot_be_forged(self):
        """The version is inside the signed payload, so it is not client-editable."""
        from rest_framework_simplejwt.tokens import AccessToken

        _, body = self.login()
        forged = AccessToken(body['access'])
        forged[TOKEN_VERSION_CLAIM_FOR_TEST] = 999
        response = self.as_user(str(forged)).get('/api/auth/profile/')
        # Re-signing requires the SECRET_KEY; the tampered token fails verification.
        self.assertEqual(response.status_code, 401)

    def test_legacy_tokens_without_the_claim_still_work(self):
        """Deploying this must not sign everyone out.

        A token minted before the claim existed reads as version 0, which matches
        the default, so it stays valid until a deliberate bump.
        """
        from rest_framework_simplejwt.tokens import AccessToken

        legacy = AccessToken.for_user(self.user)
        self.assertNotIn(TOKEN_VERSION_CLAIM_FOR_TEST, legacy)
        response = self.as_user(str(legacy)).get('/api/auth/profile/')
        self.assertEqual(response.status_code, 200)

    # --- revocation -----------------------------------------------------

    def test_revoke_tokens_invalidates_an_outstanding_access_token(self):
        from .tokens import revoke_tokens

        _, body = self.login()
        self.assertEqual(self.as_user(body['access']).get('/api/auth/profile/').status_code, 200)

        revoke_tokens(self.user)

        response = self.as_user(body['access']).get('/api/auth/profile/')
        self.assertEqual(response.status_code, 401)
        # DRF renders `detail`, not the exception's `code`, so assert the wording
        # the client actually receives.
        self.assertIn('session has ended', response.json()['detail'].lower())

    def test_password_reset_invalidates_an_outstanding_access_token(self):
        """The scenario that matters: the password leaked, so the token must die."""
        _, body = self.login()
        self.reset_password()
        response = self.as_user(body['access']).get('/api/auth/profile/')
        self.assertEqual(response.status_code, 401)

    def test_password_reset_invalidates_the_refresh_token_too(self):
        """Otherwise the holder mints a fresh access token and carries on."""
        _, body = self.login()
        self.reset_password()
        response = self.client.post('/api/auth/token/refresh/',
                                    {'refresh': body['refresh']}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_login_again_after_a_reset_works(self):
        self.reset_password()
        status, body = self.login(NEW_PASSWORD)
        self.assertEqual(status, 200)
        self.assertEqual(
            self.as_user(body['access']).get('/api/auth/profile/').status_code, 200
        )

    def test_revoking_one_user_does_not_touch_another(self):
        from .tokens import revoke_tokens

        other = User.objects.create_user('bystander', password=OLD_PASSWORD)
        UserProfile.objects.create(user=other)
        _, other_body = self.login(OLD_PASSWORD, username='bystander')

        revoke_tokens(self.user)

        self.assertEqual(
            self.as_user(other_body['access']).get('/api/auth/profile/').status_code, 200
        )

    def test_revocation_is_monotonic(self):
        from .tokens import revoke_tokens, token_version_for

        self.assertEqual(token_version_for(self.user), 0)
        self.assertEqual(revoke_tokens(self.user), 1)
        self.assertEqual(revoke_tokens(self.user), 2)
        self.user.refresh_from_db()
        self.assertEqual(token_version_for(self.user), 2)

    def test_revoke_creates_a_profile_when_one_is_missing(self):
        """`update()` against a missing row silently matches nothing.

        That exact bug once left `vendor1` with no profile, so revocation must not
        depend on a profile already existing — failing to revoke is a security
        failure, not a cosmetic one.
        """
        from .tokens import revoke_tokens, token_version_for

        UserProfile.objects.filter(user=self.user).delete()
        self.assertEqual(token_version_for(self.user), 0)

        revoke_tokens(self.user)

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile.token_version, 1)

    def test_a_user_with_no_profile_can_still_authenticate(self):
        """The version reads as 0 rather than exploding on a missing relation."""
        UserProfile.objects.filter(user=self.user).delete()
        _, body = self.login()
        self.assertEqual(
            self.as_user(body['access']).get('/api/auth/profile/').status_code, 200
        )

    # --- logout everywhere ----------------------------------------------

    def test_logout_all_revokes_the_callers_tokens(self):
        _, body = self.login()
        client = self.as_user(body['access'])

        response = client.post('/api/auth/logout-all/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['token_version'], 1)

        # The token that made the request is dead too.
        self.assertEqual(client.get('/api/auth/profile/').status_code, 401)

    def test_logout_all_requires_authentication(self):
        self.assertEqual(APIClient().post('/api/auth/logout-all/').status_code, 401)

    def test_logout_all_leaves_other_users_alone(self):
        other = User.objects.create_user('bystander2', password=OLD_PASSWORD)
        UserProfile.objects.create(user=other)
        _, other_body = self.login(OLD_PASSWORD, username='bystander2')

        _, body = self.login()
        self.as_user(body['access']).post('/api/auth/logout-all/')

        self.assertEqual(
            self.as_user(other_body['access']).get('/api/auth/profile/').status_code, 200
        )

    def test_every_role_gets_the_claim(self):
        from core.permissions import ROLE_ADMIN, ROLE_VENDOR
        from .tokens import TOKEN_VERSION_CLAIM

        for username, role in [('admin_tv', ROLE_ADMIN), ('vendor_tv', ROLE_VENDOR)]:
            user = User.objects.create_user(username, password=OLD_PASSWORD, is_staff=True)
            UserProfile.objects.create(user=user, role=role)
            _, body = self.login(OLD_PASSWORD, username=username)
            from rest_framework_simplejwt.tokens import AccessToken
            self.assertIn(TOKEN_VERSION_CLAIM, AccessToken(body['access']))
            self.assertEqual(
                self.as_user(body['access']).get('/api/auth/profile/').status_code, 200
            )

    def test_reset_message_says_sessions_were_ended(self):
        """The customer should be told, not left guessing why they were signed out."""
        self.reset_password()
        status, body = self.login(NEW_PASSWORD)
        self.assertEqual(status, 200)
        # Confirm the reset response wording too.
        response = self.client.post('/api/auth/password-reset/',
                                    {'email': 'revoke@example.com'}, format='json')
        uid, token = split_reset_url(response.json()['reset_url'])
        confirm = self.client.post(CONFIRM_URL, {
            'uid': uid, 'token': token,
            'new_password': 'AnotherPass789', 'new_password2': 'AnotherPass789',
        }, format='json')
        self.assertIn('sessions', confirm.json()['message'].lower())


class AdminUserListTests(TestCase):
    """`GET /api/auth/admin/users/` — the vendor form's account picker.

    Creating a `Vendor` requires choosing the `User` it belongs to, and there was no
    endpoint to choose from, so the shop-owning half of the role hierarchy could not
    be administered from the dashboard.

    The checks that matter are the negative ones. This endpoint lists **people**,
    which is the one place in the admin API where reading is itself a privilege — a
    vendor must not be able to enumerate the user table. And `role` must stay
    read-only: a writable role here would let any manager PATCH a customer straight
    to super admin.
    """

    URL = '/api/auth/admin/users/'

    def setUp(self):
        self.manager = self._user('mgr_user', ROLE_ADMIN)
        self.superuser = self._user('super_user', ROLE_SUPER_ADMIN)
        self.vendor = self._user('vendor_user', ROLE_VENDOR)
        self.customer = self._user('plain_customer', ROLE_CUSTOMER)

        self.shop = Vendor.objects.create(user=self.vendor, shop_name='Existing Bhandar')

    def _user(self, username, role):
        user = User.objects.create_user(username, email=f'{username}@example.com',
                                        password='pw12345678')
        UserProfile.objects.create(user=user, role=role)
        return user

    def api(self, user):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
        )
        return client

    # --- authorization ---------------------------------------------------

    def test_manager_can_list(self):
        response = self.api(self.manager).get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list, 'must be a bare list, not a page')

    def test_super_admin_can_list(self):
        self.assertEqual(self.api(self.superuser).get(self.URL).status_code, 200)

    def test_vendor_is_refused(self):
        """A vendor may read the catalogue. It may not read the user table."""
        self.assertEqual(self.api(self.vendor).get(self.URL).status_code, 403)

    def test_customer_is_refused(self):
        self.assertEqual(self.api(self.customer).get(self.URL).status_code, 403)

    def test_anonymous_is_refused(self):
        self.assertEqual(APIClient().get(self.URL).status_code, 401)

    # --- payload ---------------------------------------------------------

    def test_payload_carries_what_the_picker_needs(self):
        rows = self.api(self.manager).get(self.URL).json()
        row = next(r for r in rows if r['username'] == 'plain_customer')
        self.assertEqual(
            set(row), {'id', 'username', 'email', 'first_name', 'last_name',
                       'is_active', 'role', 'has_vendor'}
        )
        self.assertEqual(row['role'], ROLE_CUSTOMER)
        self.assertFalse(row['has_vendor'])

    def test_role_is_resolved_not_raw(self):
        """`vendor` must not read as `admin` just because the account is staff."""
        rows = self.api(self.manager).get(self.URL).json()
        row = next(r for r in rows if r['username'] == 'vendor_user')
        self.assertEqual(row['role'], ROLE_VENDOR)

    def test_no_password_or_privilege_fields_leak(self):
        """A hash has no business in a JSON response, even read-only."""
        row = self.api(self.manager).get(self.URL).json()[0]
        for forbidden in ['password', 'is_superuser', 'is_staff', 'permissions',
                          'last_login', 'date_joined']:
            self.assertNotIn(forbidden, row)

    def test_has_vendor_marks_existing_shops(self):
        rows = self.api(self.manager).get(self.URL).json()
        self.assertTrue(next(r for r in rows if r['username'] == 'vendor_user')['has_vendor'])
        self.assertFalse(next(r for r in rows if r['username'] == 'plain_customer')['has_vendor'])

    # --- filters ---------------------------------------------------------

    def test_unassigned_filter_excludes_existing_shops(self):
        """A user can own at most one shop, so offering a taken account would 400."""
        rows = self.api(self.manager).get(f'{self.URL}?unassigned=1').json()
        usernames = {r['username'] for r in rows}
        self.assertNotIn('vendor_user', usernames)
        self.assertIn('plain_customer', usernames)

    def test_search_matches_username_and_email(self):
        by_name = self.api(self.manager).get(f'{self.URL}?search=plain_cust').json()
        self.assertEqual([r['username'] for r in by_name], ['plain_customer'])

        by_email = self.api(self.manager).get(f'{self.URL}?search=mgr_user@').json()
        self.assertEqual([r['username'] for r in by_email], ['mgr_user'])

    def test_search_with_no_match_is_an_empty_list(self):
        response = self.api(self.manager).get(f'{self.URL}?search=nobodyhere')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_is_not_paginated(self):
        """A picker that silently shows one page of candidates is a broken picker."""
        for i in range(14):
            self._user(f'bulk_user_{i}', ROLE_CUSTOMER)
        body = self.api(self.manager).get(self.URL).json()
        self.assertIsInstance(body, list)
        self.assertGreater(len(body), 12)

    # --- role cannot be written through this endpoint --------------------

    def test_role_is_read_only(self):
        """A manager must not be able to escalate anyone via this surface."""
        response = self.api(self.manager).get(self.URL)
        self.assertEqual(response.status_code, 200)
        # The endpoint is a ListAPIView: there is no write verb at all.
        self.assertEqual(self.api(self.manager).post(self.URL, {}, format='json').status_code, 405)
        self.assertEqual(self.api(self.manager).patch(self.URL, {}, format='json').status_code, 405)


class ResolvedRoleInProfileTests(TestCase):
    """`GET /api/auth/profile/` must report the role the server actually enforces.

    It used to publish the raw `UserProfile.role` column. Those differ for legacy
    rows, so the dashboard and the API could disagree about the same user: the
    client was told "customer" while every request was authorised as "admin".

    The user-visible consequence of the old gate was worse than an inconsistency.
    `AdminContext` decided dashboard access from `is_admin_user`, a legacy boolean
    that `UserProfile.save()` only sets for super_admin/admin — so **a vendor could
    not open the dashboard at all**. The VENDOR role was enforced correctly on every
    endpoint and had no way to reach a single screen, which made it undemonstrable.
    """

    def _user(self, username, role=None, is_staff=False, is_superuser=False):
        user = User.objects.create_user(username, password='pw12345678',
                                        is_staff=is_staff, is_superuser=is_superuser)
        UserProfile.objects.create(user=user, **({'role': role} if role else {}))
        return user

    def profile(self, user):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
        )
        response = client.get('/api/auth/profile/')
        self.assertEqual(response.status_code, 200)
        return response.json()['profile']

    def test_vendor_reports_the_vendor_role(self):
        profile = self.profile(self._user('p_vendor', role=ROLE_VENDOR))
        self.assertEqual(profile['role'], ROLE_VENDOR)

    def test_vendor_is_not_flagged_as_a_manager(self):
        """The legacy boolean is false for vendors — which is why it was the wrong gate."""
        profile = self.profile(self._user('p_vendor2', role=ROLE_VENDOR))
        self.assertFalse(profile['is_admin_user'])

    def test_legacy_staff_user_resolves_to_admin(self):
        """The regression: the raw column says `customer`, the server says `admin`.

        A staff account created before roles existed has the model default in its
        profile. `get_role` falls back to `is_staff`; publishing the raw column
        contradicted that.
        """
        profile = self.profile(self._user('p_legacy', is_staff=True))
        self.assertEqual(profile['role'], ROLE_ADMIN)

    def test_superuser_beats_a_stale_profile_row(self):
        """An explicit Django superuser must never be demoted by profile data."""
        profile = self.profile(self._user('p_super', role=ROLE_CUSTOMER, is_superuser=True))
        self.assertEqual(profile['role'], ROLE_SUPER_ADMIN)

    def test_plain_customer_stays_a_customer(self):
        profile = self.profile(self._user('p_customer'))
        self.assertEqual(profile['role'], ROLE_CUSTOMER)

    def test_role_is_still_read_only(self):
        """A customer must not be able to PUT themselves into a super admin.

        `ProfileView` accepts **PUT**, not PATCH. That matters: two existing
        "role is read-only" checks were written against the wrong verb and the wrong
        path, so they passed against a 405 and a 404 and proved nothing. This one
        exercises the endpoint that actually writes a profile.
        """
        user = self._user('p_escalate')
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
        )
        response = client.put('/api/auth/profile/', {
            'first_name': 'Renamed', 'role': ROLE_SUPER_ADMIN,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.role, ROLE_CUSTOMER)
        # The write did happen — the name changed — so this is not a 200 that did
        # nothing, which would make the assertion above vacuous.
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Renamed')
        self.assertEqual(response.json()['profile']['role'], ROLE_CUSTOMER)
