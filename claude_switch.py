from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

INVALID_NAME_CHARS = '<>:"/\\|?*'

# Windows 文件/目录名保留名（大小写不敏感，且即使带扩展名也不可用）。
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


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
    if not name.strip():
        return "备注名不能为空，请重新输入。"

    # 目录名不能以空格或点结尾（Windows 会在某些场景自动截断/导致不可预期行为）。
    # 注意：这里必须在 strip() 之前检查尾随空格，否则校验会失效。
    if name.endswith(" ") or name.endswith("."):
        return "备注名不能以空格或点结尾。"

    normalized = name.strip()

    # Windows 保留名校验：CON/PRN/AUX/NUL/COM1-9/LPT1-9（忽略大小写，且不允许带扩展名）。
    head = normalized.split(".", 1)[0].upper()
    if head in WINDOWS_RESERVED_NAMES:
        return "备注名为 Windows 保留名，请重新输入。"

    if any(char in INVALID_NAME_CHARS for char in normalized):
        return f"备注名不能包含以下字符：{INVALID_NAME_CHARS}"
    return None


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

    summaries: list[dict] = []

    account_dirs = [path for path in target_dir.iterdir() if path.is_dir()]
    account_dirs.sort(key=lambda item: item.name)

    for account_dir in account_dirs:
        try:
            meta = read_account_meta(account_dir)

            required_keys = (
                "name",
                "detected_email",
                "updated_at",
                "last_switched_at",
                "saved_at",
            )
            has_required_strings = all(
                key in meta and isinstance(meta.get(key), str) for key in required_keys
            )

            source_paths = meta.get("source_paths")
            has_source_paths = (
                isinstance(source_paths, dict)
                and isinstance(source_paths.get("credentials"), str)
                and isinstance(source_paths.get("config"), str)
            )

            is_complete = has_required_strings and has_source_paths
            status = "正常" if is_complete else "信息不完整"

            summaries.append(
                {
                    "name": str(meta.get("name") or account_dir.name),
                    "detected_email": str(meta.get("detected_email") or ""),
                    "updated_at": str(meta.get("updated_at") or ""),
                    "last_switched_at": str(meta.get("last_switched_at") or ""),
                    "status": status,
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


def find_saved_account_name(
    current_email: str, accounts_dir: Path | None = None
) -> str | None:
    email = current_email.strip()
    if not email:
        return None

    for summary in list_account_summaries(accounts_dir):
        if summary["detected_email"] == email:
            return str(summary["name"])
    return None


def get_current_status(
    accounts_dir: Path | None = None, user_home: Path | None = None
) -> tuple[str, str]:
    config_path = get_config_path(user_home)
    email = try_read_current_email(config_path)
    if not email:
        return "未识别", "未知"

    saved_name = find_saved_account_name(email, accounts_dir)
    if saved_name:
        return email, f"已保存（{saved_name}）"

    return email, "未保存"


def build_meta(
    name: str,
    detected_email: str,
    credentials_source: Path,
    config_source: Path,
    existing_meta: dict | None = None,
) -> dict:
    current_time = now_text()
    saved_at = current_time
    last_switched_at = ""

    if existing_meta:
        previous_saved_at = existing_meta.get("saved_at")
        if isinstance(previous_saved_at, str) and previous_saved_at.strip():
            saved_at = previous_saved_at

        previous_last_switched_at = existing_meta.get("last_switched_at")
        if isinstance(previous_last_switched_at, str):
            last_switched_at = previous_last_switched_at

    return {
        "name": name,
        "detected_email": detected_email,
        "saved_at": saved_at,
        "updated_at": current_time,
        "last_switched_at": last_switched_at,
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


def ensure_account_snapshot_complete(account_dir: Path) -> None:
    required_files = (
        account_dir / "credentials.json",
        account_dir / "config.json",
        account_dir / "meta.json",
    )

    missing = [path.name for path in required_files if not path.exists()]
    if missing:
        joined = "、".join(missing)
        raise RuntimeError(f"账号档案缺少必要文件：{joined}")


def switch_account(account_dir: Path, user_home: Path | None = None) -> dict:
    ensure_account_snapshot_complete(account_dir)

    credentials_source = account_dir / "credentials.json"
    config_source = account_dir / "config.json"
    meta_path = account_dir / "meta.json"

    try:
        meta = load_json_file(meta_path)
    except (json.JSONDecodeError, OSError, ValueError) as error:
        raise RuntimeError("账号档案 meta.json 损坏，无法切换。") from error

    required_keys = (
        "name",
        "detected_email",
        "updated_at",
        "last_switched_at",
        "saved_at",
    )
    has_required_strings = all(
        key in meta and isinstance(meta.get(key), str) for key in required_keys
    )

    source_paths = meta.get("source_paths")
    has_source_paths = (
        isinstance(source_paths, dict)
        and isinstance(source_paths.get("credentials"), str)
        and isinstance(source_paths.get("config"), str)
    )

    if not (has_required_strings and has_source_paths):
        raise RuntimeError("账号档案 meta.json 字段不完整，无法切换。")

    credentials_target = get_credentials_path(user_home)
    config_target = get_config_path(user_home)
    if config_target is None:
        # 当前系统没有配置文件时，允许创建默认配置路径。
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
        raise RuntimeError("目标账号存档不存在，无法删除。")

    accounts_dir = get_accounts_dir().resolve()
    target_dir = account_dir.resolve()

    if target_dir == accounts_dir:
        raise RuntimeError("不允许删除 accounts 根目录。")

    # 必须是 accounts/ 下的直接子目录（单个账号目录）。
    if target_dir.parent != accounts_dir:
        raise RuntimeError("只能删除 accounts 下的单个账号目录。")

    shutil.rmtree(target_dir)


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
    account_name = prompt_account_name(detected_email)

    target_dir = accounts_dir / account_name
    overwrite = False
    if target_dir.exists():
        if not prompt_confirm(f"账号存档“{account_name}”已存在，是否覆盖"):
            print("已取消覆盖保存。")
            return
        overwrite = True

    try:
        save_account_snapshot(account_name, accounts_dir, overwrite=overwrite)
    except (RuntimeError, ValueError) as error:
        print(str(error))
        return

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

    try:
        delete_account_snapshot(selected["path"])
    except RuntimeError as error:
        print(str(error))
        return

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
