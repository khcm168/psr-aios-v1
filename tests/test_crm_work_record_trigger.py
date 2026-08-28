import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import crm_work_record_trigger as trigger


def make_config(**overrides):
    values = {
        "sheet_tab": "V",
        "trigger_cell": "T1",
        "trigger_value": trigger.TRIGGER_VALUE,
        "reset_value": trigger.RESET_VALUE,
        "running_value_prefix": trigger.RUNNING_VALUE_PREFIX,
        "poll_seconds": 15,
        "once": True,
        "probe": False,
        "dry_run": False,
        "company": "TOP",
        "date": "",
        "max_rows": 0,
        "start_row": 0,
        "llm_trigger_value": trigger.LLM_TRIGGER_VALUE,
        "llm_max_rows": 0,
        "llm_latest": True,
        "llm_target_column": trigger.LLM_TARGET_COLUMN,
        "llm_prompt_row": trigger.LLM_PROMPT_ROW,
        "llm_prompt": trigger.LLM_PROMPT,
        "keep_open": False,
        "watch_arm": True,
        "arm_sheet_tab": trigger.DEFAULT_ARM_SHEET_TAB,
        "arm_trigger_cell": trigger.DEFAULT_ARM_TRIGGER_CELL,
        "arm_root": Path("C:/Dev/ARM"),
    }
    values.update(overrides)
    return trigger.TriggerConfig(**values)


class CrmWorkRecordTriggerTest(unittest.TestCase):
    def test_probe_reads_trigger_without_consuming_it(self):
        config = make_config(probe=True)
        context = SimpleNamespace(spreadsheet_id="sheet-123", service=None)

        with (
            mock.patch.object(trigger, "open_sheet_context", return_value=context),
            mock.patch.object(trigger, "read_trigger_value", return_value=trigger.TRIGGER_VALUE),
            mock.patch.object(trigger, "read_cell_value", return_value="none"),
            mock.patch.object(trigger, "handle_trigger") as handle_trigger,
            mock.patch.object(trigger, "update_values") as update_values,
            mock.patch.object(trigger, "append_values") as append_values,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            trigger.run(config)

        handle_trigger.assert_not_called()
        update_values.assert_not_called()
        append_values.assert_not_called()
        self.assertIn("[PROBE] CRM armed ('work record keyin'): True", stdout.getvalue())
        self.assertIn("[PROBE] ARM trigger cell: Collection!U1", stdout.getvalue())

    def test_llm_trigger_claims_cell_before_running_polish(self):
        config = make_config(dry_run=True)
        context = SimpleNamespace(spreadsheet_id="sheet-123", service=None)
        events = []

        def fake_update(_context, _range_name, values):
            events.append(("update", values[0][0]))

        def fake_append_log(_context, _config, *, result, operation, **_kwargs):
            events.append(("log", operation, result))

        def fake_run_llm(_config):
            events.append(("run_llm", "called"))
            return 0, Path("llm.log"), "[TARGET] Rows prepared: 1\n[DONE] Preview only\n"

        def fake_reset(_context, _config):
            events.append(("reset", _config.reset_value))

        with (
            mock.patch.object(trigger, "read_trigger_value", return_value=trigger.LLM_TRIGGER_VALUE),
            mock.patch.object(trigger, "running_trigger_value", return_value="running V work record LLM>T fixed"),
            mock.patch.object(trigger, "update_values", side_effect=fake_update),
            mock.patch.object(trigger, "append_log", side_effect=fake_append_log),
            mock.patch.object(trigger, "run_llm_polish", side_effect=fake_run_llm),
            mock.patch.object(trigger, "reset_trigger_value", side_effect=fake_reset),
        ):
            trigger.handle_llm_trigger(context, config, trigger.LLM_TRIGGER_VALUE)

        self.assertEqual(
            events,
            [
                ("update", "running V work record LLM>T fixed"),
                ("log", "v-work-record-polish-trigger", "started"),
                ("run_llm", "called"),
                ("reset", trigger.RESET_VALUE),
                ("log", "v-work-record-polish-trigger", "success"),
            ],
        )

    def test_llm_command_processes_all_rows_into_columns_t_and_u_with_row_2_prompts(self):
        config = make_config()

        command = trigger.build_llm_command(config, writeback=True)
        command_text = subprocess.list2cmdline(command)

        self.assertIn("v_work_record_polish.py", command_text)
        self.assertIn("--all", command)
        self.assertIn("--target-column", command)
        self.assertIn("T,U", command)
        self.assertIn("--prompt-row", command)
        self.assertIn("2", command)
        self.assertIn("--writeback", command)

    def test_crm_command_can_start_at_requested_sheet_row(self):
        config = make_config(start_row=24)

        command = trigger.build_crm_command(config)

        self.assertIn("--start-row", command)
        self.assertIn("24", command)

    def test_arm_collection_u1_options_map_to_arm_batches(self):
        config = make_config()

        ai_command = trigger.build_arm_command(config, trigger.ARM_AI_TRIGGER_VALUE)
        mesh_command = trigger.build_arm_command(config, trigger.ARM_MESH_TRIGGER_VALUE)
        check_command = trigger.build_arm_command(config, trigger.ARM_CHECK_TRIGGER_VALUE)

        self.assertIn("cmd.exe", ai_command[0])
        self.assertIn("run_checked_remittances.bat", ai_command[-1])
        self.assertIn("run_checked_check_remittances.bat", check_command[-1])
        self.assertIn("run_checked_remittances_mesh.bat", mesh_command[-1])

    def test_handle_arm_trigger_claims_collection_u1_and_resets_on_success(self):
        config = make_config(dry_run=True)
        context = SimpleNamespace(spreadsheet_id="sheet-123", service=None)
        events = []

        def fake_update_cell(_context, sheet_tab, cell, value):
            events.append(("update_cell", sheet_tab, cell, value))

        def fake_append_log(_context, _config, *, result, operation, **_kwargs):
            events.append(("log", operation, result))

        def fake_run_arm(_config, option):
            events.append(("run_arm", option))
            return 0, Path("arm.log"), "return_code=0\n"

        with (
            mock.patch.object(trigger, "read_cell_value", return_value=trigger.ARM_AI_TRIGGER_VALUE),
            mock.patch.object(trigger, "running_cell_value", return_value="running Collection U1 ARM AI keyin fixed"),
            mock.patch.object(trigger, "update_cell_value", side_effect=fake_update_cell),
            mock.patch.object(trigger, "append_log", side_effect=fake_append_log),
            mock.patch.object(trigger, "run_arm_batch", side_effect=fake_run_arm),
        ):
            trigger.handle_arm_trigger(context, config, trigger.ARM_AI_TRIGGER_VALUE)

        self.assertEqual(
            events,
            [
                ("update_cell", "Collection", "U1", "running Collection U1 ARM AI keyin fixed"),
                ("log", "arm-collection-u1-trigger", "started"),
                ("run_arm", trigger.ARM_AI_TRIGGER_VALUE),
                ("update_cell", "Collection", "U1", trigger.RESET_VALUE),
                ("log", "arm-collection-u1-trigger", "success"),
            ],
        )

    def test_handle_trigger_claims_cell_before_running_crm(self):
        config = make_config(dry_run=True)
        context = SimpleNamespace(spreadsheet_id="sheet-123", service=None)
        events = []

        def fake_update(_context, _range_name, values):
            events.append(("update", values[0][0]))

        def fake_append_log(_context, _config, *, result, **_kwargs):
            events.append(("log", result))

        def fake_run_crm(_config):
            events.append(("run_crm", "called"))
            return 0, Path("crm.log"), "[OK] Loaded 0 sheet row(s)\n"

        def fake_reset(_context, _config):
            events.append(("reset", _config.reset_value))

        with (
            mock.patch.object(trigger, "read_trigger_value", return_value=trigger.TRIGGER_VALUE),
            mock.patch.object(trigger, "running_trigger_value", return_value="running crm work record keyin fixed"),
            mock.patch.object(trigger, "update_values", side_effect=fake_update),
            mock.patch.object(trigger, "append_log", side_effect=fake_append_log),
            mock.patch.object(trigger, "run_crm", side_effect=fake_run_crm),
            mock.patch.object(trigger, "reset_trigger_value", side_effect=fake_reset),
        ):
            trigger.handle_trigger(context, config, trigger.TRIGGER_VALUE)

        self.assertEqual(
            events,
            [
                ("update", "running crm work record keyin fixed"),
                ("log", "started"),
                ("run_crm", "called"),
                ("reset", trigger.RESET_VALUE),
                ("log", "success"),
            ],
        )

    def test_run_command_forces_child_python_utf8_output(self):
        config = make_config(dry_run=False)
        process = SimpleNamespace(stdout=["工作性質代號未填值\n"], wait=mock.Mock(return_value=1))

        with (
            mock.patch.object(trigger, "output_log_path", return_value=Path("crm.log")),
            mock.patch.object(Path, "write_text") as write_text,
            mock.patch.object(trigger.subprocess, "Popen", return_value=process) as popen,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            return_code, log_path, output = trigger.run_command(
                config,
                ["python", "child.py"],
                log_prefix="crm_work_record_lookup",
                label="CRM",
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(log_path, Path("crm.log"))
        self.assertIn("工作性質代號未填值", output)
        self.assertIn("工作性質代號未填值", stdout.getvalue())
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.STDOUT)
        write_text.assert_called_once_with(output, encoding="utf-8")

    def test_run_crm_places_watcher_cli_before_starting_selenium_child(self):
        config = make_config(dry_run=True)

        with (
            mock.patch.object(trigger, "set_console_title", return_value=True) as set_title,
            mock.patch.object(trigger, "minimize_visible_titled_windows") as minimize_windows,
            mock.patch.object(trigger, "move_console_to_half_screen", return_value=True) as move_console,
            mock.patch.object(trigger, "run_command", return_value=(0, Path("crm.log"), "")) as run_command,
        ):
            result = trigger.run_crm(config)

        self.assertEqual(result, (0, Path("crm.log"), ""))
        set_title.assert_called_once_with(trigger.CRM_WATCHER_CLI_WINDOW_TITLE)
        minimize_windows.assert_called_once_with()
        move_console.assert_called_once_with(
            "worker",
            title_text=trigger.CRM_WATCHER_CLI_WINDOW_TITLE,
            fallback_to_console_window=False,
        )
        run_command.assert_called_once()


if __name__ == "__main__":
    unittest.main()
