from __future__ import annotations

import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "ydotool-tui"
APP = runpy.run_path(str(SCRIPT))
REMOTE_HOST = "example-host"


class KeyComboTests(unittest.TestCase):
    def test_expands_common_combo_spellings(self) -> None:
        parse = APP["parse_key_combo"]
        self.assertEqual(parse("ctrl-alt-t"), ["ctrl", "alt", "t"])
        self.assertEqual(parse("c-a-t"), ["ctrl", "alt", "t"])
        self.assertEqual(parse("alt-f2"), ["alt", "f2"])
        self.assertEqual(parse("super-r"), ["leftmeta", "r"])
        self.assertEqual(parse("ctrl-shift-esc"), ["ctrl", "shift", "esc"])

    def test_expands_symbol_aliases(self) -> None:
        parse = APP["parse_key_combo"]
        self.assertEqual(parse("ctrl-plus"), ["ctrl", "shift", "equal"])
        self.assertEqual(parse("ctrl-slash"), ["ctrl", "slash"])
        self.assertEqual(parse("ctrl-?"), ["ctrl", "shift", "slash"])

    def test_rejects_unknown_and_empty_combo(self) -> None:
        parse = APP["parse_key_combo"]
        with self.assertRaisesRegex(ValueError, "Expected a key combo"):
            parse("")
        with self.assertRaisesRegex(ValueError, "Unknown key: nope"):
            parse("ctrl-nope")


class ControllerDryRunTests(unittest.TestCase):
    def make_controller(self, **overrides: object):
        kwargs = {
            "ssh_target": None,
            "ydotool": "ydotool",
            "dry_run": True,
            "socket_path": None,
            "key_delay": 12,
        }
        kwargs.update(overrides)
        return APP["Controller"](**kwargs)

    def test_key_press_uses_down_then_reverse_up_events(self) -> None:
        controller = self.make_controller()
        controller.key(["ctrl", "alt", "t"])
        self.assertEqual(
            controller.last_command,
            "ydotool key --key-delay 12 29:1 56:1 20:1 20:0 56:0 29:0",
        )
        self.assertEqual(controller.last_status, "Dry run")

    def test_remote_command_is_quoted_for_ssh(self) -> None:
        controller = self.make_controller(ssh_target=REMOTE_HOST)
        controller.key(["alt", "f2"])
        self.assertEqual(
            controller.last_command,
            "ssh example-host 'ydotool key --key-delay 12 56:1 60:1 60:0 56:0'",
        )

    def test_socket_prefix_is_included_locally_and_remotely(self) -> None:
        local = self.make_controller(socket_path="/tmp/ydotool socket")
        local.click("left")
        self.assertEqual(
            local.last_command,
            "'YDOTOOL_SOCKET=/tmp/ydotool socket' ydotool click 0xC0",
        )

        remote = self.make_controller(ssh_target=REMOTE_HOST, socket_path="/tmp/ydotool socket")
        remote.click("left")
        self.assertEqual(
            remote.last_command,
            "ssh example-host ''\"'\"'YDOTOOL_SOCKET=/tmp/ydotool socket'\"'\"' ydotool click 0xC0'",
        )

    def test_mouse_commands_use_option_terminators(self) -> None:
        controller = self.make_controller(ssh_target=REMOTE_HOST)
        controller.move(0, -1)
        self.assertEqual(
            controller.last_command,
            "ssh example-host 'ydotool mousemove -- 0 -1'",
        )

        controller.wheel(0, 1)
        self.assertEqual(
            controller.last_command,
            "ssh example-host 'ydotool mousemove --wheel -- 0 1'",
        )

    def test_click_variants(self) -> None:
        controller = self.make_controller()
        controller.click("left", 2)
        self.assertEqual(controller.last_command, "ydotool click --repeat 2 0xC0")

        controller.click("forward")
        self.assertEqual(controller.last_command, "ydotool click 0xC5")


class ControllerQueueTests(unittest.TestCase):
    def make_controller(self):
        return APP["Controller"](
            ssh_target=None,
            ydotool="ydotool",
            dry_run=False,
            socket_path=None,
            key_delay=12,
        )

    def test_commands_are_queued_until_tick_starts_them(self) -> None:
        controller = self.make_controller()
        controller.click("left")

        self.assertEqual(controller.last_command, "ydotool click 0xC0")
        self.assertEqual(controller.last_status, "Queued (1)")
        self.assertEqual(len(controller.pending), 1)
        self.assertIsNone(controller.current)

    def test_tick_runs_one_command_at_a_time(self) -> None:
        controller = self.make_controller()
        controller.click("left")
        controller.click("right")

        first = FakeProcess()
        second = FakeProcess()
        with patch.object(APP["subprocess"], "Popen", side_effect=[first, second]) as popen:
            controller.tick()
            self.assertIs(controller.current, first)
            self.assertEqual(controller.last_status, "Running, 1 queued")
            self.assertEqual(popen.call_count, 1)
            args, kwargs = popen.call_args
            self.assertEqual(args, (["ydotool", "click", "0xC0"],))
            self.assertEqual(kwargs["stdin"], APP["subprocess"].DEVNULL)
            self.assertIsInstance(kwargs["env"], dict)
            self.assertEqual(kwargs["stdout"], APP["subprocess"].PIPE)
            self.assertEqual(kwargs["stderr"], APP["subprocess"].PIPE)
            self.assertTrue(kwargs["text"])

            first.returncode = 0
            controller.tick()
            self.assertIs(controller.current, second)
            self.assertEqual(controller.last_status, "Running")
            self.assertEqual(popen.call_count, 2)

            second.returncode = 0
            controller.tick()
            self.assertIsNone(controller.current)
            self.assertEqual(controller.last_status, "Sent")

    def test_failed_command_reports_last_output_line(self) -> None:
        controller = self.make_controller()
        controller.click("left")

        process = FakeProcess(returncode=2, stderr="first line\nbad option\n")
        with patch.object(APP["subprocess"], "Popen", return_value=process):
            controller.tick()
            controller.tick()

        self.assertEqual(controller.last_status, "bad option")

    def test_close_terminates_running_command_and_clears_queue(self) -> None:
        controller = self.make_controller()
        controller.click("left")
        controller.click("right")

        process = FakeProcess()
        with patch.object(APP["subprocess"], "Popen", return_value=process):
            controller.tick()
            controller.close()

        self.assertTrue(process.terminated)
        self.assertIsNone(controller.current)
        self.assertEqual(len(controller.pending), 0)


class FakeProcess:
    def __init__(self, returncode: int | None = None, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def communicate(self) -> tuple[str, str]:
        return self.stdout, self.stderr

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: int | None = None) -> int | None:
        return self.returncode


class ActionAndMouseBindingTests(unittest.TestCase):
    def test_representative_actions_send_expected_commands(self) -> None:
        actions = {action.label: action for action in APP["build_actions"]()}
        controller = APP["Controller"](
            ssh_target=None,
            ydotool="ydotool",
            dry_run=True,
            socket_path=None,
            key_delay=12,
        )

        actions["Ctrl+Alt+T"].run(controller)
        self.assertEqual(
            controller.last_command,
            "ydotool key --key-delay 12 29:1 56:1 20:1 20:0 56:0 29:0",
        )

        actions["Double click"].run(controller)
        self.assertEqual(controller.last_command, "ydotool click --repeat 2 0xC0")

        self.assertNotIn("Alt+F2", actions)

    def test_mouse_direction_bindings(self) -> None:
        direction = APP["mouse_direction_for_key"]
        self.assertEqual(direction("w"), (0, -1))
        self.assertEqual(direction("a"), (-1, 0))
        self.assertEqual(direction("s"), (0, 1))
        self.assertEqual(direction("d"), (1, 0))
        self.assertIsNone(direction("h"))

    def test_mouse_click_and_wheel_bindings(self) -> None:
        clicks = APP["MOUSE_CLICKS"]
        wheels = APP["MOUSE_WHEELS"]
        self.assertEqual(clicks["2"], ("left", 2, "Double click"))
        self.assertEqual(clicks["b"], ("back", 1, "Back click"))
        self.assertEqual(clicks["f"], ("forward", 1, "Forward click"))

        self.assertEqual(wheels["h"], (1, 0, "Wheel left"))
        self.assertEqual(wheels["j"], (0, -1, "Wheel down"))
        self.assertEqual(wheels["k"], (0, 1, "Wheel up"))
        self.assertEqual(wheels["l"], (-1, 0, "Wheel right"))


if __name__ == "__main__":
    unittest.main()
