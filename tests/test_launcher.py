import asyncio
import importlib.util
import re
import unittest
from types import SimpleNamespace as NS
from unittest import mock

HAVE_PTB = importlib.util.find_spec("telegram") is not None

if HAVE_PTB:
    from telegram.constants import ChatMemberStatus
    from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut
    import bot as launcher
    from bot import SubscriptionStatus

HOSTILE_NAMES = [
    r"¯\_(ツ)_/¯",
    "<b>not bold</b> & <script>alert(1)</script>",
    "*bold* _italic_ `code` [link](http://x)",
    "a < b > c && d",
]

TAG = re.compile(r"</?(b|i)>")


def assert_valid_html(testcase, text):
    """Only <b> and <i> may appear, balanced; everything else must be escaped."""
    stripped = TAG.sub("", text)
    testcase.assertNotIn("<", stripped, text)
    testcase.assertNotIn(">", stripped, text)
    testcase.assertIsNone(re.search(r"&(?!amp;|lt;|gt;|quot;|#x27;)", stripped), text)
    stack = []
    for tag in re.findall(r"</?(?:b|i)>", text):
        if tag.startswith("</"):
            testcase.assertTrue(stack and stack.pop() == tag[2], f"unbalanced: {text}")
        else:
            stack.append(tag[1])
    testcase.assertEqual(stack, [], f"unclosed tags: {text}")


class FakeBot:
    id = 4242

    def __init__(self):
        self.status = ChatMemberStatus.MEMBER if HAVE_PTB else None
        self.is_member = True
        self.error = None
        self.calls = 0
        self.sent = []

    async def get_chat_member(self, chat_id, user_id):
        self.calls += 1
        if self.error:
            raise self.error
        return NS(status=self.status, is_member=self.is_member)

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.sent.append((chat_id, text, reply_markup))


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, reply_markup=None, **kwargs):
        self.replies.append((text, reply_markup))


class FakeQuery:
    def __init__(self, bot, user_id, data, first_name="Name", edit_error=None):
        self.bot = bot
        self.from_user = NS(id=user_id, first_name=first_name)
        self.data = data
        self.edit_error = edit_error
        self.edits, self.answers = [], []

    async def edit_message_text(self, text, reply_markup=None, **kwargs):
        if self.edit_error:
            raise self.edit_error
        self.edits.append((text, reply_markup))

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    def get_bot(self):
        return self.bot


def message_update(user_id=1, first_name="Name"):
    return NS(message=FakeMessage(), callback_query=None,
              effective_user=NS(id=user_id, first_name=first_name))


def callback_update(query):
    return NS(message=None, callback_query=query, effective_user=query.from_user)


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


@unittest.skipUnless(HAVE_PTB, "python-telegram-bot is not installed")
class LauncherTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = FakeBot()
        self.context = NS(bot=self.bot)
        for name, value in (("CHANNEL_USERNAME", "@testchannel"), ("CHANNEL_URL", "https://t.me/testchannel")):
            patcher = mock.patch.object(launcher, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class SubscriptionStatusTests(LauncherTestCase):
    async def test_member_statuses(self):
        for status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            self.bot.status = status
            self.assertIs(await launcher.get_subscription_status(self.bot, 1), SubscriptionStatus.SUBSCRIBED)

    async def test_not_members(self):
        for status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            self.bot.status = status
            self.assertIs(await launcher.get_subscription_status(self.bot, 1), SubscriptionStatus.NOT_SUBSCRIBED)

    async def test_restricted_member_counts(self):
        self.bot.status, self.bot.is_member = ChatMemberStatus.RESTRICTED, True
        self.assertIs(await launcher.get_subscription_status(self.bot, 1), SubscriptionStatus.SUBSCRIBED)
        self.bot.is_member = False
        self.assertIs(await launcher.get_subscription_status(self.bot, 1), SubscriptionStatus.NOT_SUBSCRIBED)

    async def test_telegram_errors_are_unknown_never_subscribed(self):
        for error in (NetworkError("down"), TimedOut(), BadRequest("Chat not found"), Forbidden("not a member")):
            self.bot.error = error
            with self.assertLogs("bot", level="WARNING"):
                self.assertIs(await launcher.get_subscription_status(self.bot, 1), SubscriptionStatus.UNKNOWN)

    async def test_configuration_errors_are_logged_louder_than_outages(self):
        self.bot.error = BadRequest("Chat not found")
        with self.assertLogs("bot", level="ERROR"):
            await launcher.get_subscription_status(self.bot, 1)
        self.bot.error = NetworkError("down")
        with self.assertLogs("bot", level="WARNING") as logs:
            await launcher.get_subscription_status(self.bot, 1)
        self.assertEqual(logs.records[0].levelname, "WARNING")

    async def test_programming_errors_are_not_swallowed(self):
        self.bot.error = AttributeError("a bug, not a Telegram problem")
        with self.assertRaises(AttributeError):
            await launcher.get_subscription_status(self.bot, 1)


class StartTests(LauncherTestCase):
    async def test_subscriber_gets_the_menu_with_all_bots(self):
        update = message_update()
        await launcher.start(update, self.context)
        text, markup = update.message.replies[-1]
        self.assertIn("Welcome", text)
        self.assertEqual([b.callback_data for b in buttons(markup)], list(launcher.BOT_DESCRIPTIONS))

    async def test_non_subscriber_gets_the_subscribe_screen(self):
        self.bot.status = ChatMemberStatus.LEFT
        update = message_update()
        await launcher.start(update, self.context)
        text, markup = update.message.replies[-1]
        self.assertIn("@testchannel", text)
        self.assertEqual(buttons(markup)[0].url, "https://t.me/testchannel")
        self.assertEqual(buttons(markup)[1].callback_data, "check_subscription")

    async def test_outage_gives_a_retry_screen_not_an_accusation(self):
        self.bot.error = NetworkError("down")
        update = message_update()
        with self.assertLogs("bot", level="WARNING"):
            await launcher.start(update, self.context)
        text, markup = update.message.replies[-1]
        self.assertIn("try again", text.lower())
        self.assertNotIn("you need to subscribe", text)
        self.assertEqual([(b.callback_data, b.url) for b in buttons(markup)], [("check_subscription", None)])

    async def test_menu_is_not_shown_during_an_outage(self):
        self.bot.error = NetworkError("down")
        update = message_update()
        with self.assertLogs("bot", level="WARNING"):
            await launcher.start(update, self.context)
        self.assertNotIn("Choose a bot", update.message.replies[-1][0])


class EscapingTests(LauncherTestCase):
    async def test_hostile_names_never_break_the_html(self):
        for name in HOSTILE_NAMES:
            with self.subTest(name=name):
                for status in (ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT):
                    self.bot.status = status
                    update = message_update(first_name=name)
                    await launcher.start(update, self.context)
                    assert_valid_html(self, update.message.replies[-1][0])
                self.bot.status = ChatMemberStatus.MEMBER
                query = FakeQuery(self.bot, 1, "bot1", first_name=name)
                await launcher.button_handler(callback_update(query), self.context)
                assert_valid_html(self, query.edits[-1][0])

    async def test_name_appears_as_plain_text(self):
        update = message_update(first_name=r"¯\_(ツ)_/¯")
        await launcher.start(update, self.context)
        self.assertIn(r"¯\_(ツ)_/¯", update.message.replies[-1][0], "no stray backslashes added")

    async def test_every_static_screen_is_valid_html(self):
        for key in launcher.BOT_DESCRIPTIONS:
            query = FakeQuery(self.bot, 1, key)
            await launcher.button_handler(callback_update(query), self.context)
            assert_valid_html(self, query.edits[-1][0])
        update = message_update()
        await launcher.help_command(update, self.context)
        assert_valid_html(self, update.message.replies[-1][0])

    async def test_channel_name_is_escaped(self):
        self.bot.status = ChatMemberStatus.LEFT
        with mock.patch.object(launcher, "CHANNEL_USERNAME", "@a&b<c>"):
            update = message_update()
            await launcher.start(update, self.context)
        assert_valid_html(self, update.message.replies[-1][0])


class ButtonTests(LauncherTestCase):
    async def test_bot_info_for_a_subscriber(self):
        query = FakeQuery(self.bot, 1, "bot3")
        await launcher.button_handler(callback_update(query), self.context)
        text, markup = query.edits[-1]
        self.assertIn("Anonymous Voice Chat", text)
        go, back = buttons(markup)
        self.assertEqual(go.url, launcher.BOT_DESCRIPTIONS["bot3"]["link"])
        self.assertEqual(back.callback_data, "back_to_menu")

    async def test_bot_info_for_a_non_subscriber_shows_the_subscribe_screen(self):
        self.bot.status = ChatMemberStatus.LEFT
        query = FakeQuery(self.bot, 1, "bot3")
        await launcher.button_handler(callback_update(query), self.context)
        self.assertIn("subscribe", query.answers[0][0])
        self.assertIn("@testchannel", query.edits[-1][0])

    async def test_bot_info_during_an_outage_keeps_the_screen(self):
        self.bot.error = NetworkError("down")
        query = FakeQuery(self.bot, 1, "bot3")
        with self.assertLogs("bot", level="WARNING"):
            await launcher.button_handler(callback_update(query), self.context)
        self.assertEqual(query.edits, [], "the current message must not be replaced")
        text, show_alert = query.answers[-1]
        self.assertTrue(show_alert)
        self.assertIn("try again", text.lower())

    async def test_check_subscription_paths(self):
        self.bot.status = ChatMemberStatus.LEFT
        query = FakeQuery(self.bot, 1, "check_subscription")
        await launcher.button_handler(callback_update(query), self.context)
        self.assertEqual(query.answers[-1][0], "❌ You are not subscribed to the channel")
        self.assertIn("@testchannel", query.edits[-1][0])

        self.bot.error = NetworkError("down")
        query = FakeQuery(self.bot, 1, "check_subscription")
        with self.assertLogs("bot", level="WARNING"):
            await launcher.button_handler(callback_update(query), self.context)
        self.assertNotIn("not subscribed", query.answers[-1][0])
        self.assertEqual(query.edits, [])

        self.bot.error = None
        self.bot.status = ChatMemberStatus.MEMBER
        query = FakeQuery(self.bot, 1, "check_subscription")
        await launcher.button_handler(callback_update(query), self.context)
        self.assertEqual(query.answers[-1][0], "✅ Subscription confirmed!")
        self.assertIn("Choose a bot", query.edits[-1][0])

    async def test_back_and_unknown_buttons(self):
        query = FakeQuery(self.bot, 1, "back_to_menu")
        await launcher.button_handler(callback_update(query), self.context)
        self.assertIn("Choose a bot", query.edits[-1][0])
        query = FakeQuery(self.bot, 1, "something_else")
        await launcher.button_handler(callback_update(query), self.context)
        self.assertEqual((query.edits, query.answers), ([], [(None, False)]))

    async def test_menu_buttons_match_the_descriptions(self):
        update = message_update()
        await launcher.start(update, self.context)
        menu = [b.callback_data for b in buttons(update.message.replies[-1][1])]
        self.assertEqual(menu, list(launcher.BOT_DESCRIPTIONS))
        for key, info in launcher.BOT_DESCRIPTIONS.items():
            self.assertTrue(info["link"].startswith("https://t.me/"), key)
            self.assertTrue(info["name"] and info["title"] and info["description"], key)


class RenderTests(LauncherTestCase):
    async def test_not_modified_is_ignored(self):
        query = FakeQuery(self.bot, 1, "x", edit_error=BadRequest("Message is not modified"))
        await launcher.render(callback_update(query), "text", None)
        self.assertEqual(self.bot.sent, [])

    async def test_an_uneditable_message_is_replaced_by_a_new_one(self):
        query = FakeQuery(self.bot, 7, "x", edit_error=BadRequest("Message can't be edited"))
        with self.assertLogs("bot", level="WARNING"):
            await launcher.render(callback_update(query), "hello", None)
        self.assertEqual([(c, t) for c, t, _ in self.bot.sent], [(7, "hello")])


@unittest.skipUnless(HAVE_PTB, "python-telegram-bot is not installed")
class StartupTests(unittest.IsolatedAsyncioTestCase):
    def app(self, bot):
        return NS(bot=bot)

    async def test_wrong_channel_or_missing_rights_stop_the_bot_with_a_clear_message(self):
        for error in (BadRequest("Chat not found"), Forbidden("bot is not a member")):
            bot = FakeBot(); bot.error = error
            with mock.patch.object(launcher, "CHANNEL_USERNAME", "@testchannel"):
                with self.assertRaises(launcher.ConfigurationError) as caught:
                    await launcher.verify_channel_access(self.app(bot))
            self.assertIn("administrator", str(caught.exception))
            self.assertIn("@testchannel", str(caught.exception))

    async def test_a_temporary_problem_at_startup_does_not_prevent_starting(self):
        bot = FakeBot(); bot.error = NetworkError("down")
        with self.assertLogs("bot", level="WARNING"):
            await launcher.verify_channel_access(self.app(bot))

    async def test_non_admin_bot_gets_a_warning_and_admin_does_not(self):
        bot = FakeBot(); bot.status = ChatMemberStatus.MEMBER
        with self.assertLogs("bot", level="WARNING") as logs:
            await launcher.verify_channel_access(self.app(bot))
        self.assertIn("not an administrator", logs.output[0])
        bot.status = ChatMemberStatus.ADMINISTRATOR
        await launcher.verify_channel_access(self.app(bot))


@unittest.skipUnless(HAVE_PTB, "python-telegram-bot is not installed")
class ConfigTests(unittest.TestCase):
    def test_main_refuses_to_start_without_settings(self):
        cases = [
            ({"TOKEN": "", "CHANNEL_USERNAME": "@c", "CHANNEL_URL": "https://t.me/c"}, "BOT_TOKEN"),
            ({"TOKEN": "1:A", "CHANNEL_USERNAME": "", "CHANNEL_URL": ""}, "CHANNEL_USERNAME"),
            ({"TOKEN": "1:A", "CHANNEL_USERNAME": "-1001234567", "CHANNEL_URL": ""}, "CHANNEL_URL"),
        ]
        for values, expected in cases:
            with self.subTest(expected=expected):
                with mock.patch.multiple(launcher, **values):
                    with self.assertRaises(SystemExit) as caught:
                        launcher.main()
                self.assertIn(expected, str(caught.exception))

    def test_channel_url_is_derived_from_a_public_username(self):
        derive = launcher.derive_channel_url
        self.assertEqual(derive("@ChronoRoom"), "https://t.me/ChronoRoom")
        self.assertEqual(derive("ChronoRoom"), "https://t.me/ChronoRoom")
        self.assertEqual(derive("@ChronoRoom", " https://t.me/+invite "), "https://t.me/+invite", "explicit URL wins")
        self.assertEqual(derive("-1001234567"), "", "a private channel needs an explicit URL")
        self.assertEqual(derive(""), "")
        self.assertEqual(derive("@a b"), "")


if __name__ == "__main__":
    unittest.main()
