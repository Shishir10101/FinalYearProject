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

from .models import UserProfile
from .password_reset import build_reset_url, encode_uid, make_token

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
