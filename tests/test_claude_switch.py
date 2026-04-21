import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import claude_switch


class HelperFunctionTests(unittest.TestCase):
    def test_get_config_path_prefers_dot_claude_config(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".claude").mkdir()
            (home / ".claude" / ".config.json").write_text("{}", encoding="utf-8")
            (home / ".claude.json").write_text('{"legacy": true}', encoding="utf-8")

            result = claude_switch.get_config_path(home)

            self.assertEqual(result, home / ".claude" / ".config.json")

    def test_get_config_path_falls_back_to_legacy_file(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".claude.json").write_text("{}", encoding="utf-8")

            result = claude_switch.get_config_path(home)

            self.assertEqual(result, home / ".claude.json")

    def test_get_config_path_returns_none_when_no_config_files_exist(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = claude_switch.get_config_path(home)

            self.assertIsNone(result)

    def test_validate_account_name_rejects_blank_input(self):
        message = claude_switch.validate_account_name("   \t\r\n  ")
        self.assertEqual(message, "备注名不能为空，请重新输入。")

    def test_validate_account_name_rejects_windows_reserved_name(self):
        message = claude_switch.validate_account_name("CON")
        self.assertEqual(message, "备注名为 Windows 保留名，请重新输入。")

    def test_validate_account_name_rejects_name_ending_with_dot(self):
        message = claude_switch.validate_account_name("工作号.")
        self.assertEqual(message, "备注名不能以空格或点结尾。")

    def test_validate_account_name_rejects_invalid_characters(self):
        message = claude_switch.validate_account_name("主号*")
        self.assertEqual(message, '备注名不能包含以下字符：<>:"/\\|?*')

    def test_validate_account_name_rejects_name_ending_with_space(self):
        message = claude_switch.validate_account_name("工作号 ")
        self.assertEqual(message, "备注名不能以空格或点结尾。")

    def test_validate_account_name_accepts_name_with_leading_spaces(self):
        message = claude_switch.validate_account_name("  工作号")
        self.assertIsNone(message)

    def test_get_user_home_uses_provided_path(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(claude_switch.get_user_home(home), home)

    def test_get_credentials_path_uses_user_home(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(
                claude_switch.get_credentials_path(home),
                home / ".claude" / ".credentials.json",
            )


class StatusAndListingTests(unittest.TestCase):
    def test_try_read_current_email_returns_value(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".config.json"
            config_path.write_text(
                '{"oauthAccount": {"emailAddress": "abc@example.com"}}',
                encoding="utf-8",
            )

            result = claude_switch.try_read_current_email(config_path)

            self.assertEqual(result, "abc@example.com")

    def test_try_read_current_email_returns_empty_when_missing(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".config.json"
            config_path.write_text("{}", encoding="utf-8")

            result = claude_switch.try_read_current_email(config_path)

            self.assertEqual(result, "")

    def test_list_account_summaries_marks_broken_meta(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            good_dir = accounts_dir / "主号"
            broken_dir = accounts_dir / "坏档案"
            good_dir.mkdir(parents=True)
            broken_dir.mkdir(parents=True)

            (good_dir / "meta.json").write_text(
                '{"name": "主号", "detected_email": "abc@example.com", '
                '"updated_at": "2026-04-21 20:30:00", "last_switched_at": ""}',
                encoding="utf-8",
            )
            (broken_dir / "meta.json").write_text("{not-json}", encoding="utf-8")

            result = claude_switch.list_account_summaries(accounts_dir)

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["name"], "主号")
            self.assertEqual(result[1]["status"], "异常")

    def test_list_account_summaries_marks_incomplete_meta_fields(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            incomplete_dir = accounts_dir / "不完整档案"
            incomplete_dir.mkdir(parents=True)

            # meta.json 存在且 JSON 有效，但字段不完整（缺少 detected_email）。
            (incomplete_dir / "meta.json").write_text(
                '{"name": "不完整档案", "updated_at": "2026-04-21 20:30:00", "last_switched_at": "", '
                '"saved_at": "2026-04-21 20:30:00", "source_paths": {"credentials": "c.json", "config": "cfg.json"}}',
                encoding="utf-8",
            )

            result = claude_switch.list_account_summaries(accounts_dir)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "不完整档案")
            self.assertEqual(result[0]["status"], "信息不完整")

    def test_list_account_summaries_marks_incomplete_when_missing_saved_at(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            incomplete_dir = accounts_dir / "缺少saved_at"
            incomplete_dir.mkdir(parents=True)

            (incomplete_dir / "meta.json").write_text(
                '{"name": "缺少saved_at", "detected_email": "abc@example.com", '
                '"updated_at": "2026-04-21 20:30:00", "last_switched_at": "", '
                '"source_paths": {"credentials": "c.json", "config": "cfg.json"}}',
                encoding="utf-8",
            )

            result = claude_switch.list_account_summaries(accounts_dir)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "缺少saved_at")
            self.assertEqual(result[0]["status"], "信息不完整")

    def test_list_account_summaries_marks_incomplete_when_missing_source_paths(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            incomplete_dir = accounts_dir / "缺少source_paths"
            incomplete_dir.mkdir(parents=True)

            (incomplete_dir / "meta.json").write_text(
                '{"name": "缺少source_paths", "detected_email": "abc@example.com", '
                '"updated_at": "2026-04-21 20:30:00", "last_switched_at": "", '
                '"saved_at": "2026-04-21 20:30:00"}',
                encoding="utf-8",
            )

            result = claude_switch.list_account_summaries(accounts_dir)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "缺少source_paths")
            self.assertEqual(result[0]["status"], "信息不完整")

    def test_list_account_summaries_marks_incomplete_when_missing_source_paths_child_key(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            incomplete_dir = accounts_dir / "缺少source_paths子键"
            incomplete_dir.mkdir(parents=True)

            (incomplete_dir / "meta.json").write_text(
                '{"name": "缺少source_paths子键", "detected_email": "abc@example.com", '
                '"updated_at": "2026-04-21 20:30:00", "last_switched_at": "", '
                '"saved_at": "2026-04-21 20:30:00", "source_paths": {"credentials": "c.json"}}',
                encoding="utf-8",
            )

            result = claude_switch.list_account_summaries(accounts_dir)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "缺少source_paths子键")
            self.assertEqual(result[0]["status"], "信息不完整")

    def test_get_current_status_returns_saved_name(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            (home / ".claude").mkdir(parents=True)
            accounts_dir.mkdir()
            (home / ".claude" / ".config.json").write_text(
                '{"oauthAccount": {"emailAddress": "abc@example.com"}}',
                encoding="utf-8",
            )
            (home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
            saved_dir = accounts_dir / "主号"
            saved_dir.mkdir()
            (saved_dir / "meta.json").write_text(
                '{"name": "主号", "detected_email": "abc@example.com", '
                '"updated_at": "2026-04-21 20:30:00", "last_switched_at": ""}',
                encoding="utf-8",
            )

            email, status_text = claude_switch.get_current_status(accounts_dir, home)

            self.assertEqual(email, "abc@example.com")
            self.assertEqual(status_text, "已保存（主号）")


class SaveSnapshotTests(unittest.TestCase):
    def test_save_account_snapshot_creates_files_and_meta(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            (home / ".claude").mkdir(parents=True)
            accounts_dir.mkdir()
            (home / ".claude" / ".credentials.json").write_text(
                '{"token": "abc"}',
                encoding="utf-8",
            )
            (home / ".claude" / ".config.json").write_text(
                '{"oauthAccount": {"emailAddress": "abc@example.com"}}',
                encoding="utf-8",
            )

            meta = claude_switch.save_account_snapshot("主号", accounts_dir, home)

            account_dir = accounts_dir / "主号"
            self.assertTrue((account_dir / "credentials.json").exists())
            self.assertTrue((account_dir / "config.json").exists())
            self.assertEqual(meta["name"], "主号")
            self.assertEqual(meta["detected_email"], "abc@example.com")
            self.assertEqual(meta["last_switched_at"], "")
            self.assertIn("source_paths", meta)
            self.assertIn("credentials", meta["source_paths"])
            self.assertIn("config", meta["source_paths"])

    def test_save_account_snapshot_preserves_saved_at_on_overwrite(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            account_dir = accounts_dir / "主号"
            (home / ".claude").mkdir(parents=True)
            account_dir.mkdir(parents=True)
            (home / ".claude" / ".credentials.json").write_text(
                '{"token": "new"}', encoding="utf-8"
            )
            (home / ".claude" / ".config.json").write_text(
                '{"oauthAccount": {"emailAddress": "abc@example.com"}}',
                encoding="utf-8",
            )
            (account_dir / "meta.json").write_text(
                '{"name": "主号", "detected_email": "old@example.com", '
                '"saved_at": "2026-04-20 18:00:00", "updated_at": "2026-04-20 18:00:00", '
                '"last_switched_at": "", "source_paths": {"credentials": "old", "config": "old"}}',
                encoding="utf-8",
            )

            meta = claude_switch.save_account_snapshot(
                "主号", accounts_dir, home, overwrite=True
            )

            self.assertEqual(meta["saved_at"], "2026-04-20 18:00:00")
            self.assertEqual(meta["detected_email"], "abc@example.com")
            self.assertNotEqual(meta["updated_at"], "2026-04-20 18:00:00")

    def test_save_account_snapshot_requires_existing_source_files(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            home.mkdir(parents=True)
            accounts_dir.mkdir()

            with self.assertRaises(RuntimeError):
                claude_switch.save_account_snapshot("主号", accounts_dir, home)


class SwitchAndDeleteTests(unittest.TestCase):
    def test_switch_account_restores_files_and_updates_last_switched_at(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            account_dir = accounts_dir / "主号"
            (home / ".claude").mkdir(parents=True)
            account_dir.mkdir(parents=True)

            (home / ".claude" / ".credentials.json").write_text(
                '{"token": "old"}', encoding="utf-8"
            )
            (home / ".claude" / ".config.json").write_text(
                '{"oauthAccount": {"emailAddress": "old@example.com"}}',
                encoding="utf-8",
            )

            (account_dir / "credentials.json").write_text(
                '{"token": "new"}', encoding="utf-8"
            )
            (account_dir / "config.json").write_text(
                '{"oauthAccount": {"emailAddress": "new@example.com"}}',
                encoding="utf-8",
            )
            (account_dir / "meta.json").write_text(
                '{"name": "主号", "detected_email": "new@example.com", '
                '"saved_at": "2026-04-21 18:00:00", "updated_at": "2026-04-21 18:00:00", '
                '"last_switched_at": "", "source_paths": {"credentials": "x", "config": "y"}}',
                encoding="utf-8",
            )

            meta = claude_switch.switch_account(account_dir, home)

            self.assertIn(
                '"token": "new"',
                (home / ".claude" / ".credentials.json").read_text(encoding="utf-8"),
            )
            self.assertIn(
                '"new@example.com"',
                (home / ".claude" / ".config.json").read_text(encoding="utf-8"),
            )
            self.assertTrue(meta["last_switched_at"])

    def test_switch_account_rejects_incomplete_account(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            account_dir = Path(tmp) / "accounts" / "坏档案"
            (home / ".claude").mkdir(parents=True)
            account_dir.mkdir(parents=True)
            (account_dir / "meta.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                claude_switch.switch_account(account_dir, home)

    def test_delete_account_snapshot_removes_directory(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            account_dir = accounts_dir / "测试号"
            account_dir.mkdir(parents=True)
            (account_dir / "meta.json").write_text("{}", encoding="utf-8")

            with patch.object(claude_switch, "get_accounts_dir", return_value=accounts_dir):
                claude_switch.delete_account_snapshot(account_dir)

            self.assertFalse(account_dir.exists())

    def test_delete_account_snapshot_rejects_missing_directory(self):
        with TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "accounts" / "不存在"

            with self.assertRaises(RuntimeError):
                claude_switch.delete_account_snapshot(account_dir)

    def test_delete_account_snapshot_rejects_accounts_root_directory(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            accounts_dir.mkdir(parents=True)

            with patch.object(claude_switch, "get_accounts_dir", return_value=accounts_dir):
                with self.assertRaises(RuntimeError) as ctx:
                    claude_switch.delete_account_snapshot(accounts_dir)

            self.assertIn("不允许删除 accounts 根目录", str(ctx.exception))

    def test_delete_account_snapshot_rejects_directory_outside_accounts(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            outside_dir = Path(tmp) / "outside"
            accounts_dir.mkdir(parents=True)
            outside_dir.mkdir(parents=True)

            with patch.object(claude_switch, "get_accounts_dir", return_value=accounts_dir):
                with self.assertRaises(RuntimeError) as ctx:
                    claude_switch.delete_account_snapshot(outside_dir)

            self.assertIn("只能删除 accounts 下的单个账号目录", str(ctx.exception))

    def test_switch_account_rejects_incomplete_meta_even_when_files_exist(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            account_dir = Path(tmp) / "accounts" / "主号"
            (home / ".claude").mkdir(parents=True)
            account_dir.mkdir(parents=True)

            (account_dir / "credentials.json").write_text("{}", encoding="utf-8")
            (account_dir / "config.json").write_text("{}", encoding="utf-8")
            # meta.json JSON 有效但字段缺失：缺少 detected_email、saved_at 等。
            (account_dir / "meta.json").write_text('{"name": "主号", "updated_at": "2026-04-21 18:00:00"}', encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                claude_switch.switch_account(account_dir, home)

            self.assertIn("meta.json 字段不完整", str(ctx.exception))


class MenuInteractionTests(unittest.TestCase):
    def test_bat_launcher_does_not_use_pause(self):
        bat_path = claude_switch.get_base_dir() / "claude_switch.bat"
        content = bat_path.read_text(encoding="utf-8")

        self.assertNotIn("pause", content.lower())

    def test_print_account_list_shows_empty_message(self):
        with patch("builtins.print") as mock_print:
            claude_switch.print_account_list([])

        mock_print.assert_called_once_with("当前没有已保存账号。")

    def test_choose_account_returns_none_on_invalid_index(self):
        summaries = [
            {
                "name": "主号",
                "detected_email": "a@example.com",
                "updated_at": "2026-04-21 20:30:00",
                "last_switched_at": "",
                "status": "正常",
                "path": Path("/tmp/main"),
            }
        ]

        with patch("builtins.input", return_value="9"):
            selected = claude_switch.choose_account(summaries, "切换")

        self.assertIsNone(selected)

    def test_handle_switch_cancels_when_windows_not_closed_confirmed(self):
        accounts_dir = Path("/tmp/accounts")
        summaries = [
            {
                "name": "主号",
                "detected_email": "a@example.com",
                "updated_at": "2026-04-21 20:30:00",
                "last_switched_at": "",
                "status": "正常",
                "path": Path("/tmp/accounts/main"),
            }
        ]

        with patch.object(claude_switch, "list_account_summaries", return_value=summaries), patch.object(
            claude_switch, "choose_account", return_value=summaries[0]
        ), patch.object(claude_switch, "prompt_confirm", return_value=False), patch.object(
            claude_switch, "switch_account"
        ) as mock_switch, patch("builtins.print") as mock_print:
            claude_switch.handle_switch(accounts_dir)

        mock_switch.assert_not_called()
        mock_print.assert_any_call("未确认关闭窗口，已取消切换。")

    def test_handle_save_cancels_when_overwrite_not_confirmed(self):
        with TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / "accounts"
            accounts_dir.mkdir(parents=True)
            (accounts_dir / "主号").mkdir()

            with patch.object(claude_switch, "get_config_path", return_value=Path(tmp) / "cfg.json"), patch.object(
                claude_switch, "get_credentials_path", return_value=Path(tmp) / "cred.json"
            ), patch.object(claude_switch, "try_read_current_email", return_value="abc@example.com"), patch.object(
                claude_switch, "prompt_account_name", return_value="主号"
            ), patch.object(claude_switch, "prompt_confirm", return_value=False), patch.object(
                claude_switch, "save_account_snapshot"
            ) as mock_save, patch("builtins.print") as mock_print:
                (Path(tmp) / "cfg.json").write_text("{}", encoding="utf-8")
                (Path(tmp) / "cred.json").write_text("{}", encoding="utf-8")

                claude_switch.handle_save(accounts_dir)

            mock_save.assert_not_called()
            mock_print.assert_any_call("已取消覆盖保存。")


if __name__ == "__main__":
    unittest.main()
