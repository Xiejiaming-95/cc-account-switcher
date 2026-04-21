# Claude 本地账号轻量切换工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个仅面向 Windows 本地环境的 Claude 账号快照切换工具，支持保存、切换、查看、删除账号存档，并通过 bat 入口启动。

**Architecture:** 使用 `claude_switch.py` 作为唯一业务实现文件，在单文件内按路径检测、档案读写、状态计算、菜单交互分组组织函数。`claude_switch.bat` 只负责调用 Python 脚本并保留窗口，不承载业务逻辑；自动化验证以标准库 `unittest` 为主，菜单级流程用模拟 `USERPROFILE` 的手工走查补足。

**Tech Stack:** Python 3.10+、标准库（`json`、`shutil`、`pathlib`、`datetime`、`unittest`）、Windows batch

---

## File Structure

- `claude_switch.py`
  - 主程序文件
  - 包含路径检测、邮箱识别、档案保存/切换/删除、列表展示、菜单循环
- `claude_switch.bat`
  - bat 启动入口
  - 调用 `python claude_switch.py`，执行后 `pause`
- `tests/test_claude_switch.py`
  - 标准库 `unittest` 测试
  - 只覆盖不依赖真实 Claude 进程的逻辑：路径优先级、备注名校验、状态计算、meta 读写、档案切换、删除

## Shared Decisions

- 当前配置文件路径优先级固定为：`%USERPROFILE%/.claude/.config.json` → `%USERPROFILE%/.claude.json`
- 当前凭据文件固定为：`%USERPROFILE%/.claude/.credentials.json`
- 当前账号识别字段固定为：`oauthAccount.emailAddress`
- 备注名允许中文、英文、数字、空格；去除首尾空格后不能为空；禁止 `< > : " / \\ | ? *`
- 切换前必须要求用户明确确认所有 Claude 相关窗口已关闭
- 用户可见文本全部中文
- 操作完成后统一返回主菜单

### Task 1: 建立基础文件与纯函数助手

**Files:**
- Create: `claude_switch.py`
- Create: `tests/test_claude_switch.py`

- [ ] **Step 1: 写出失败的基础测试**

将 `tests/test_claude_switch.py` 写成下面内容：

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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

    def test_validate_account_name_rejects_invalid_characters(self):
        message = claude_switch.validate_account_name('主号*')
        self.assertEqual(message, '备注名不能包含以下字符：<>:"/\\|?*')

    def test_validate_account_name_accepts_trimmed_name(self):
        message = claude_switch.validate_account_name('  工作号  ')
        self.assertIsNone(message)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: FAIL，提示 `ModuleNotFoundError: No module named 'claude_switch'`

- [ ] **Step 3: 写入最小实现让测试通过**

创建 `claude_switch.py`，先写入下面内容：

```python
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

INVALID_NAME_CHARS = '<>:"/\\|?*'


def get_base_dir() -> Path:
    return Path(__file__).resolve().parent


def get_accounts_dir() -> Path:
    return get_base_dir() / "accounts"


def get_user_home(user_home: Path | None = None) -> Path:
    if user_home is not None:
        return Path(user_home)
    return Path(os.environ.get("USERPROFILE", str(Path.home())))


def get_credentials_path(user_home: Path | None = None) -> Path:
    home = get_user_home(user_home)
    return home / ".claude" / ".credentials.json"


def get_config_path(user_home: Path | None = None) -> Path | None:
    home = get_user_home(user_home)
    primary = home / ".claude" / ".config.json"
    legacy = home / ".claude.json"
    if primary.exists():
        return primary
    if legacy.exists():
        return legacy
    return None


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def validate_account_name(name: str) -> str | None:
    normalized = name.strip()
    if not normalized:
        return "备注名不能为空，请重新输入。"
    if any(char in INVALID_NAME_CHARS for char in normalized):
        return f"备注名不能包含以下字符：{INVALID_NAME_CHARS}"
    return None


def main() -> None:
    print("Claude 本地账号切换工具尚未实现完整菜单。")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 重新运行测试并确认通过**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: PASS，4 个测试全部通过

- [ ] **Step 5: 提交这一小步**

```bash
git add claude_switch.py tests/test_claude_switch.py
git commit -m "test: add helper coverage for path resolution"
```

### Task 2: 实现当前账号识别、状态计算与列表读取

**Files:**
- Modify: `claude_switch.py`
- Modify: `tests/test_claude_switch.py`

- [ ] **Step 1: 先补失败测试，锁定状态与列表行为**

在 `tests/test_claude_switch.py` 末尾追加下面测试类：

```python

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
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: FAIL，提示缺少 `try_read_current_email`、`list_account_summaries`、`get_current_status`

- [ ] **Step 3: 在主程序中补齐状态与列表函数**

在 `claude_switch.py` 中加入下面函数定义：

```python
import json


def load_json_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        return data
    raise ValueError(f"JSON 根节点不是对象：{path}")


def try_read_current_email(config_path: Path | None) -> str:
    if config_path is None or not config_path.exists():
        return ""
    try:
        data = load_json_file(config_path)
    except (json.JSONDecodeError, OSError, ValueError):
        return ""
    oauth_account = data.get("oauthAccount")
    if not isinstance(oauth_account, dict):
        return ""
    email = oauth_account.get("emailAddress")
    if isinstance(email, str):
        return email.strip()
    return ""


def read_account_meta(account_dir: Path) -> dict:
    meta_path = account_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(meta_path)
    return load_json_file(meta_path)


def list_account_summaries(accounts_dir: Path | None = None) -> list[dict]:
    target_dir = Path(accounts_dir) if accounts_dir is not None else get_accounts_dir()
    if not target_dir.exists():
        return []

    summaries = []
    for account_dir in sorted((path for path in target_dir.iterdir() if path.is_dir()), key=lambda item: item.name):
        try:
            meta = read_account_meta(account_dir)
            summaries.append(
                {
                    "name": str(meta.get("name") or account_dir.name),
                    "detected_email": str(meta.get("detected_email") or ""),
                    "updated_at": str(meta.get("updated_at") or ""),
                    "last_switched_at": str(meta.get("last_switched_at") or ""),
                    "status": "正常",
                    "path": account_dir,
                }
            )
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            summaries.append(
                {
                    "name": account_dir.name,
                    "detected_email": "",
                    "updated_at": "",
                    "last_switched_at": "",
                    "status": "异常",
                    "path": account_dir,
                }
            )
    return summaries


def find_saved_account_name(current_email: str, accounts_dir: Path | None = None) -> str | None:
    email = current_email.strip()
    if not email:
        return None
    for summary in list_account_summaries(accounts_dir):
        if summary["detected_email"] == email:
            return summary["name"]
    return None


def get_current_status(accounts_dir: Path | None = None, user_home: Path | None = None) -> tuple[str, str]:
    config_path = get_config_path(user_home)
    email = try_read_current_email(config_path)
    if not email:
        return "未识别", "未知"
    saved_name = find_saved_account_name(email, accounts_dir)
    if saved_name:
        return email, f"已保存（{saved_name}）"
    return email, "未保存"
```

- [ ] **Step 4: 重新运行测试并确认通过**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: PASS，8 个测试全部通过

- [ ] **Step 5: 提交这一小步**

```bash
git add claude_switch.py tests/test_claude_switch.py
git commit -m "feat: add current account status detection"
```

### Task 3: 实现账号保存与 meta 生成

**Files:**
- Modify: `claude_switch.py`
- Modify: `tests/test_claude_switch.py`

- [ ] **Step 1: 先补失败测试，锁定保存行为**

在 `tests/test_claude_switch.py` 末尾追加下面测试类：

```python

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

    def test_save_account_snapshot_preserves_saved_at_on_overwrite(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            account_dir = accounts_dir / "主号"
            (home / ".claude").mkdir(parents=True)
            account_dir.mkdir(parents=True)
            (home / ".claude" / ".credentials.json").write_text('{"token": "new"}', encoding="utf-8")
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

            meta = claude_switch.save_account_snapshot("主号", accounts_dir, home, overwrite=True)

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
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: FAIL，提示缺少 `save_account_snapshot` 或保存行为不符合预期

- [ ] **Step 3: 补齐 meta 生成与保存逻辑**

在 `claude_switch.py` 中加入下面函数：

```python

def build_meta(
    name: str,
    detected_email: str,
    credentials_source: Path,
    config_source: Path,
    existing_meta: dict | None = None,
) -> dict:
    current_time = now_text()
    saved_at = current_time
    if existing_meta:
        previous_saved_at = existing_meta.get("saved_at")
        if isinstance(previous_saved_at, str) and previous_saved_at.strip():
            saved_at = previous_saved_at
    return {
        "name": name,
        "detected_email": detected_email,
        "saved_at": saved_at,
        "updated_at": current_time,
        "last_switched_at": "" if not existing_meta else str(existing_meta.get("last_switched_at") or ""),
        "source_paths": {
            "credentials": credentials_source.as_posix(),
            "config": config_source.as_posix(),
        },
    }


def save_account_snapshot(
    account_name: str,
    accounts_dir: Path | None = None,
    user_home: Path | None = None,
    overwrite: bool = False,
) -> dict:
    error_message = validate_account_name(account_name)
    if error_message is not None:
        raise ValueError(error_message)

    target_accounts_dir = Path(accounts_dir) if accounts_dir is not None else get_accounts_dir()
    target_accounts_dir.mkdir(parents=True, exist_ok=True)

    credentials_path = get_credentials_path(user_home)
    config_path = get_config_path(user_home)
    if not credentials_path.exists():
        raise RuntimeError("未找到 Claude 凭据文件，无法保存当前账号。")
    if config_path is None or not config_path.exists():
        raise RuntimeError("未找到 Claude 配置文件，无法保存当前账号。")

    normalized_name = account_name.strip()
    target_dir = target_accounts_dir / normalized_name
    existing_meta = None
    if target_dir.exists():
        if not overwrite:
            raise FileExistsError(f"账号存档已存在：{normalized_name}")
        meta_path = target_dir / "meta.json"
        if meta_path.exists():
            try:
                existing_meta = load_json_file(meta_path)
            except (json.JSONDecodeError, OSError, ValueError):
                existing_meta = None
    else:
        target_dir.mkdir(parents=True)

    detected_email = try_read_current_email(config_path)
    shutil.copy2(credentials_path, target_dir / "credentials.json")
    shutil.copy2(config_path, target_dir / "config.json")

    meta = build_meta(
        normalized_name,
        detected_email,
        credentials_path,
        config_path,
        existing_meta,
    )
    meta_path = target_dir / "meta.json"
    with meta_path.open("w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False, indent=2)
    return meta
```

同时将文件头部 import 改成下面形式：

```python
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
```

- [ ] **Step 4: 重新运行测试并确认通过**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: PASS，11 个测试全部通过

- [ ] **Step 5: 提交这一小步**

```bash
git add claude_switch.py tests/test_claude_switch.py
git commit -m "feat: add account snapshot save flow"
```

### Task 4: 实现切换、删除与账号完整性校验

**Files:**
- Modify: `claude_switch.py`
- Modify: `tests/test_claude_switch.py`

- [ ] **Step 1: 先补失败测试，锁定切换与删除行为**

在 `tests/test_claude_switch.py` 末尾追加下面测试类：

```python

class SwitchAndDeleteTests(unittest.TestCase):
    def test_switch_account_restores_files_and_updates_last_switched_at(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            accounts_dir = Path(tmp) / "accounts"
            account_dir = accounts_dir / "主号"
            (home / ".claude").mkdir(parents=True)
            account_dir.mkdir(parents=True)
            (home / ".claude" / ".credentials.json").write_text('{"token": "old"}', encoding="utf-8")
            (home / ".claude" / ".config.json").write_text(
                '{"oauthAccount": {"emailAddress": "old@example.com"}}',
                encoding="utf-8",
            )
            (account_dir / "credentials.json").write_text('{"token": "new"}', encoding="utf-8")
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

            self.assertIn('"token": "new"', (home / ".claude" / ".credentials.json").read_text(encoding="utf-8"))
            self.assertIn('"new@example.com"', (home / ".claude" / ".config.json").read_text(encoding="utf-8"))
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
            account_dir = Path(tmp) / "accounts" / "测试号"
            account_dir.mkdir(parents=True)
            (account_dir / "meta.json").write_text("{}", encoding="utf-8")

            claude_switch.delete_account_snapshot(account_dir)

            self.assertFalse(account_dir.exists())
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: FAIL，提示缺少 `switch_account`、`delete_account_snapshot` 或切换行为不符合预期

- [ ] **Step 3: 补齐切换与删除核心逻辑**

在 `claude_switch.py` 中加入下面函数：

```python

def ensure_account_snapshot_complete(account_dir: Path) -> None:
    required_files = [
        account_dir / "credentials.json",
        account_dir / "config.json",
        account_dir / "meta.json",
    ]
    missing = [path.name for path in required_files if not path.exists()]
    if missing:
        joined = "、".join(missing)
        raise RuntimeError(f"账号档案缺少必要文件：{joined}")


def switch_account(account_dir: Path, user_home: Path | None = None) -> dict:
    ensure_account_snapshot_complete(account_dir)

    credentials_source = account_dir / "credentials.json"
    config_source = account_dir / "config.json"
    meta_path = account_dir / "meta.json"
    meta = load_json_file(meta_path)

    credentials_target = get_credentials_path(user_home)
    config_target = get_config_path(user_home)
    if config_target is None:
        config_target = get_user_home(user_home) / ".claude" / ".config.json"

    credentials_target.parent.mkdir(parents=True, exist_ok=True)
    config_target.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(credentials_source, credentials_target)
    shutil.copy2(config_source, config_target)

    meta["last_switched_at"] = now_text()
    with meta_path.open("w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False, indent=2)
    return meta


def delete_account_snapshot(account_dir: Path) -> None:
    if not account_dir.exists() or not account_dir.is_dir():
        raise RuntimeError("目标账号存档不存在。")
    shutil.rmtree(account_dir)
```

- [ ] **Step 4: 重新运行测试并确认通过**

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: PASS，14 个测试全部通过

- [ ] **Step 5: 提交这一小步**

```bash
git add claude_switch.py tests/test_claude_switch.py
git commit -m "feat: add account switch and delete flows"
```

### Task 5: 完成菜单交互与 bat 入口

**Files:**
- Modify: `claude_switch.py`
- Create: `claude_switch.bat`

- [ ] **Step 1: 先补齐最终交互所需的展示与输入函数**

在 `claude_switch.py` 中加入下面展示与输入函数：

```python

def print_header() -> None:
    print("==============================")
    print(" Claude 本地账号切换工具")
    print("==============================")


def print_main_menu() -> None:
    print()
    print("1. 保存当前账号")
    print("2. 切换到已保存账号")
    print("3. 查看账号列表")
    print("4. 删除账号存档")
    print("5. 退出")
    print()


def prompt_confirm(message: str) -> bool:
    answer = input(f"{message}（y/n）：").strip().lower()
    return answer == "y"


def prompt_account_name(default_name: str) -> str:
    while True:
        if default_name:
            raw_name = input(f"请输入备注名（直接回车使用 {default_name}）：")
            account_name = default_name if not raw_name.strip() else raw_name.strip()
        else:
            account_name = input("请输入备注名：").strip()
        error_message = validate_account_name(account_name)
        if error_message is None:
            return account_name.strip()
        print(error_message)


def prompt_menu_choice() -> str:
    return input("请输入编号：").strip()


def print_account_list(summaries: list[dict]) -> None:
    if not summaries:
        print("当前没有已保存账号。")
        return
    for index, summary in enumerate(summaries, start=1):
        email = summary["detected_email"] or "未识别邮箱"
        updated_at = summary["updated_at"] or "信息不完整"
        switched_at = summary["last_switched_at"] or "未切换"
        status = "" if summary["status"] == "正常" else f" | {summary['status']}"
        print(
            f"{index}. {summary['name']} | {email} | 更新: {updated_at} | 最近切换: {switched_at}{status}"
        )
```

- [ ] **Step 2: 补齐四个菜单动作与主循环**

将 `claude_switch.py` 末尾替换为下面内容：

```python

def handle_save(accounts_dir: Path) -> None:
    config_path = get_config_path()
    credentials_path = get_credentials_path()
    if config_path is None or not config_path.exists():
        print("未找到 Claude 配置文件，无法保存当前账号。")
        return
    if not credentials_path.exists():
        print("未找到 Claude 凭据文件，无法保存当前账号。")
        return

    detected_email = try_read_current_email(config_path)
    default_name = detected_email
    account_name = prompt_account_name(default_name)
    target_dir = accounts_dir / account_name
    overwrite = False
    if target_dir.exists():
        if not prompt_confirm(f"账号存档“{account_name}”已存在，是否覆盖"):
            print("已取消覆盖保存。")
            return
        overwrite = True

    save_account_snapshot(account_name, accounts_dir, overwrite=overwrite)
    print(f"保存成功：{account_name}")


def choose_account(summaries: list[dict], action_text: str) -> dict | None:
    if not summaries:
        print(f"当前没有可{action_text}的账号存档。")
        return None
    print_account_list(summaries)
    raw_value = input("请输入编号：").strip()
    if not raw_value.isdigit():
        print("输入无效，请输入列表中的编号。")
        return None
    index = int(raw_value)
    if index < 1 or index > len(summaries):
        print("输入无效，请输入列表中的编号。")
        return None
    return summaries[index - 1]


def handle_switch(accounts_dir: Path) -> None:
    summaries = list_account_summaries(accounts_dir)
    selected = choose_account(summaries, "切换")
    if selected is None:
        return
    if not prompt_confirm("请确认所有 Claude 相关窗口都已关闭"):
        print("未确认关闭窗口，已取消切换。")
        return
    try:
        switch_account(selected["path"])
    except RuntimeError as error:
        print(str(error))
        return
    print("切换完成，请手动重新打开 Claude。")


def handle_list(accounts_dir: Path) -> None:
    summaries = list_account_summaries(accounts_dir)
    print_account_list(summaries)


def handle_delete(accounts_dir: Path) -> None:
    summaries = list_account_summaries(accounts_dir)
    selected = choose_account(summaries, "删除")
    if selected is None:
        return
    if not prompt_confirm(f"确认删除账号存档“{selected['name']}”"):
        print("已取消删除。")
        return
    delete_account_snapshot(selected["path"])
    print(f"删除完成：{selected['name']}")


def main() -> None:
    accounts_dir = get_accounts_dir()
    accounts_dir.mkdir(parents=True, exist_ok=True)

    while True:
        print_header()
        current_email, status_text = get_current_status(accounts_dir)
        print(f"当前登录账号：{current_email}")
        print(f"当前账号状态：{status_text}")
        print_main_menu()

        choice = prompt_menu_choice()
        print()
        if choice == "1":
            handle_save(accounts_dir)
        elif choice == "2":
            handle_switch(accounts_dir)
        elif choice == "3":
            handle_list(accounts_dir)
        elif choice == "4":
            handle_delete(accounts_dir)
        elif choice == "5":
            print("已退出。")
            break
        else:
            print("输入无效，请输入 1 到 5。")

        print()
        input("按回车键返回主菜单...")
        print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 创建 bat 启动入口**

创建 `claude_switch.bat`：

```bat
@echo off
setlocal
python "%~dp0claude_switch.py"
pause
```

- [ ] **Step 4: 运行语法检查与全部自动化测试**

Run: `python -m py_compile claude_switch.py`
Expected: 无输出，退出码为 0

Run: `python -m unittest tests/test_claude_switch.py -v`
Expected: PASS，14 个测试全部通过

- [ ] **Step 5: 做菜单级手工走查并提交最终实现**

先用下面命令准备模拟环境：

```bash
python - <<'PY'
from pathlib import Path
import json

root = Path('.tmp_home')
(root / '.claude').mkdir(parents=True, exist_ok=True)
(root / '.claude' / '.credentials.json').write_text('{"token": "main-token"}', encoding='utf-8')
(root / '.claude' / '.config.json').write_text(
    json.dumps({"oauthAccount": {"emailAddress": "main@example.com"}}, ensure_ascii=False, indent=2),
    encoding='utf-8',
)
PY
```

再在模拟 `USERPROFILE` 下启动程序：

```bash
USERPROFILE="$PWD/.tmp_home" python claude_switch.py
```

按下面顺序手工走查：
- 首页显示 `当前登录账号：main@example.com`
- 首页显示 `当前账号状态：未保存`
- 选择 `1` 保存当前账号，备注名填 `主号`
- 返回主菜单后再次确认状态显示 `已保存（主号）`
- 选择 `3` 查看列表，确认出现 `主号 | main@example.com`
- 修改 `.tmp_home/.claude/.config.json` 与 `.credentials.json` 为另一个账号内容，再保存成 `备用号`
- 选择 `2` 切换到 `主号`，先确认关闭窗口，再检查 `.tmp_home/.claude/` 下文件已恢复为主号内容
- 选择 `4` 删除 `备用号`，确认二次确认生效，且只删除 `accounts/备用号/`
- 最后使用 `cmd /c claude_switch.bat` 验证 bat 能拉起脚本并在结束后保留窗口

完成后提交：

```bash
git add claude_switch.py claude_switch.bat tests/test_claude_switch.py
git commit -m "feat: add claude local account switcher"
```

## Self-Review

### Spec coverage

- 启动显示当前登录账号与保存状态：Task 2、Task 5
- 保存当前账号：Task 3、Task 5
- 切换到已保存账号且需先确认关闭窗口：Task 4、Task 5
- 查看账号列表且单个坏档案不影响整体：Task 2、Task 5
- 删除账号存档且需二次确认：Task 4、Task 5
- 路径优先级、邮箱识别字段、meta 字段：Task 1、Task 2、Task 3
- bat 入口：Task 5
- 格式检查、自动化检查、菜单级手工走查：Task 5

### Placeholder scan

- 未使用 `TBD`、`TODO`、`implement later`、`fill in details`
- 每个代码步骤都提供了实际代码
- 每个验证步骤都提供了实际命令与预期结果

### Type consistency

- 账号列表统一使用 `list[dict]`
- `get_current_status` 始终返回 `(current_email, status_text)`
- 删除函数统一命名为 `delete_account_snapshot`
- 切换函数统一命名为 `switch_account`
- 列表项统一包含 `name`、`detected_email`、`updated_at`、`last_switched_at`、`status`、`path`
