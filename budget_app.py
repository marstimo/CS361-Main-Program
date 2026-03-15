import json
import os
import time
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, date
from typing import Any, Dict, List, Optional

DATA_FILE = "expenses.json"
BG = "#f1f1f1"

CATEGORY_CONFIG_FILE = "category_rules_config.json"
RECURRING_RULES_FILE = "recurring_rules.json"

CATEGORY_REQUEST_FILE = "category_rules_request.json"
CATEGORY_DONE_FILE = "category_rules_done.json"
CATEGORY_ERROR_FILE = "category_rules_error.json"

SUMMARY_REQUEST_FILE = "budget_summary_request.json"
SUMMARY_DONE_FILE = "budget_summary_done.json"
SUMMARY_ERROR_FILE = "budget_summary_error.json"

RECURRING_REQUEST_FILE = "recurring_expenses_request.json"
RECURRING_DONE_FILE = "recurring_expenses_done.json"
RECURRING_ERROR_FILE = "recurring_expenses_error.json"

HISTORY_REQUEST_FILE = "history_request.json"
HISTORY_RESPONSE_FILE = "history_response.json"
HISTORY_LOCK_FILE = "history_request.lock"

SERVICE_TIMEOUT_SECONDS = 5.0
SERVICE_POLL_SECONDS = 0.05


def safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_json_atomic(path: str, data: Any) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    os.replace(tmp_path, path)


def wait_for_file(paths: List[str], timeout_seconds: float = SERVICE_TIMEOUT_SECONDS) -> Optional[str]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for path in paths:
            if os.path.exists(path):
                return path
        time.sleep(SERVICE_POLL_SECONDS)
    return None


def parse_expense_date(expense: Dict[str, Any]) -> Optional[date]:
    created_at = str(expense.get("created_at", "")).strip()
    if not created_at:
        return None

    try:
        return datetime.fromisoformat(created_at).date()
    except ValueError:
        try:
            return date.fromisoformat(created_at[:10])
        except ValueError:
            return None


def ensure_default_category_config() -> None:
    if os.path.exists(CATEGORY_CONFIG_FILE):
        return

    default_config = {
        "allowedCategories": [
            "Food",
            "Transport",
            "Housing",
            "Utilities",
            "Entertainment",
            "Shopping",
            "Healthcare",
            "Education",
            "Savings",
            "Subscriptions",
            "Income",
            "Other"
        ],
        "aliases": {
            "groceries": "Food",
            "grocery": "Food",
            "restaurant": "Food",
            "uber": "Transport",
            "lyft": "Transport",
            "gas": "Transport",
            "rent": "Housing",
            "electric": "Utilities",
            "internet": "Utilities",
            "netflix": "Subscriptions",
            "spotify": "Subscriptions",
            "school": "Education",
            "medical": "Healthcare",
            "fun": "Entertainment",
            "misc": "Other"
        }
    }
    write_json_atomic(CATEGORY_CONFIG_FILE, default_config)


def ensure_default_recurring_rules() -> None:
    if not os.path.exists(RECURRING_RULES_FILE):
        write_json_atomic(RECURRING_RULES_FILE, [])

def update_category_in_config(old_name: str, new_name: str) -> str:
    old_clean = normalize_category_name(old_name)
    new_clean = normalize_category_name(new_name)

    if not old_clean:
        raise ValueError("Select a category to update.")
    if not new_clean:
        raise ValueError("New category name cannot be empty.")

    config = load_category_config()
    allowed = [str(item).strip() for item in config.get("allowedCategories", []) if str(item).strip()]
    aliases = dict(config.get("aliases", {}))

    old_index = None
    for i, existing in enumerate(allowed):
        if existing.casefold() == old_clean.casefold():
            old_index = i
            break

    if old_index is None:
        raise ValueError("Category not found.")

    for i, existing in enumerate(allowed):
        if i != old_index and existing.casefold() == new_clean.casefold():
            raise ValueError("Another category already uses that name.")

    allowed[old_index] = new_clean

    for alias_key, alias_value in list(aliases.items()):
        if str(alias_value).strip().casefold() == old_clean.casefold():
            aliases[alias_key] = new_clean

    config["allowedCategories"] = sorted(
        list({item.strip(): item.strip() for item in allowed if item.strip()}.values()),
        key=str.casefold
    )
    config["aliases"] = aliases
    save_category_config(config)

    expenses = load_expenses()
    changed = False
    for expense in expenses:
        category = str(expense.get("category", "")).strip()
        if category.casefold() == old_clean.casefold():
            expense["category"] = new_clean
            changed = True
    if changed:
        save_expenses(expenses)

    rules = load_recurring_rules()
    changed_rules = False
    for rule in rules:
        category = str(rule.get("category", "")).strip()
        if category.casefold() == old_clean.casefold():
            rule["category"] = new_clean
            changed_rules = True
    if changed_rules:
        save_recurring_rules(rules)

    return new_clean


def delete_category_from_config(category_name: str) -> None:
    target = normalize_category_name(category_name)
    if not target:
        raise ValueError("Select a category to delete.")

    config = load_category_config()
    allowed = [str(item).strip() for item in config.get("allowedCategories", []) if str(item).strip()]
    aliases = dict(config.get("aliases", {}))

    new_allowed = [item for item in allowed if item.casefold() != target.casefold()]
    if len(new_allowed) == len(allowed):
        raise ValueError("Category not found.")

    for alias_key, alias_value in list(aliases.items()):
        if str(alias_value).strip().casefold() == target.casefold():
            del aliases[alias_key]

    config["allowedCategories"] = sorted(new_allowed, key=str.casefold)
    config["aliases"] = aliases
    save_category_config(config)

    expenses = load_expenses()
    changed = False
    for expense in expenses:
        category = str(expense.get("category", "")).strip()
        if category.casefold() == target.casefold():
            expense["category"] = "Other"
            changed = True
    if changed:
        save_expenses(expenses)

    rules = load_recurring_rules()
    changed_rules = False
    for rule in rules:
        category = str(rule.get("category", "")).strip()
        if category.casefold() == target.casefold():
            rule["category"] = "Other"
            changed_rules = True
    if changed_rules:
        save_recurring_rules(rules)

def load_category_config() -> Dict[str, Any]:
    ensure_default_category_config()
    try:
        config = read_json(CATEGORY_CONFIG_FILE)
    except (OSError, json.JSONDecodeError):
        config = {}

    if not isinstance(config, dict):
        config = {}

    allowed = config.get("allowedCategories", [])
    aliases = config.get("aliases", {})

    if not isinstance(allowed, list):
        allowed = []
    if not isinstance(aliases, dict):
        aliases = {}

    clean_allowed = []
    for item in allowed:
        if isinstance(item, str) and item.strip():
            clean_allowed.append(item.strip())

    clean_aliases: Dict[str, str] = {}
    for key, value in aliases.items():
        if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip():
            clean_aliases[key.strip()] = value.strip()

    return {
        "allowedCategories": clean_allowed,
        "aliases": clean_aliases
    }


def save_category_config(config: Dict[str, Any]) -> None:
    write_json_atomic(CATEGORY_CONFIG_FILE, config)


def normalize_category_name(name: str) -> str:
    parts = [part for part in name.strip().split() if part]
    return " ".join(part.capitalize() for part in parts)


def get_all_categories() -> List[str]:
    config = load_category_config()
    categories = []
    seen = set()

    for item in config.get("allowedCategories", []):
        cleaned = normalize_category_name(str(item))
        if cleaned and cleaned.casefold() not in seen:
            categories.append(cleaned)
            seen.add(cleaned.casefold())

    categories.sort(key=str.casefold)
    return categories


def add_category_to_config(raw_name: str) -> str:
    name = normalize_category_name(raw_name)
    if not name:
        raise ValueError("Category name cannot be empty.")

    config = load_category_config()
    allowed = config.get("allowedCategories", [])

    for existing in allowed:
        if str(existing).strip().casefold() == name.casefold():
            return str(existing).strip()

    allowed.append(name)
    allowed = sorted(
        [str(item).strip() for item in allowed if str(item).strip()],
        key=str.casefold
    )
    config["allowedCategories"] = allowed
    save_category_config(config)
    return name


def load_expenses() -> List[Dict[str, Any]]:
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            try:
                amt = float(item.get("amount"))
                cat = str(item.get("category", "")).strip()
                ts = str(item.get("created_at", "")).strip()
                if amt <= 0 or not cat or not ts:
                    continue

                normalized = dict(item)
                normalized["amount"] = amt
                normalized["category"] = cat
                normalized["created_at"] = ts
                out.append(normalized)
            except (TypeError, ValueError):
                continue

        return out
    except (OSError, json.JSONDecodeError):
        return []


def save_expenses(expenses: List[Dict[str, Any]]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(expenses, f, indent=2)
    except OSError:
        messagebox.showwarning("Save failed", "Could not save expenses to disk.")


def get_date_bounds(expenses: List[Dict[str, Any]]) -> tuple[str, str]:
    dates: List[date] = []
    for expense in expenses:
        d = parse_expense_date(expense)
        if d is not None:
            dates.append(d)

    if not dates:
        today = date.today().isoformat()
        return today, today

    return min(dates).isoformat(), max(dates).isoformat()


def get_month_bounds(target: date) -> tuple[str, str]:
    start = date(target.year, target.month, 1)
    if target.month == 12:
        next_month = date(target.year + 1, 1, 1)
    else:
        next_month = date(target.year, target.month + 1, 1)
    end = date.fromordinal(next_month.toordinal() - 1)
    return start.isoformat(), end.isoformat()


def get_year_bounds(target: date) -> tuple[str, str]:
    return date(target.year, 1, 1).isoformat(), date(target.year, 12, 31).isoformat()


def send_standard_service_request(
    request_file: str,
    done_file: str,
    error_file: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    safe_remove(done_file)
    safe_remove(error_file)
    safe_remove(request_file)

    write_json_atomic(request_file, payload)

    result_file = wait_for_file([done_file, error_file])
    if result_file is None:
        raise TimeoutError(f"Timed out waiting for service response for {request_file}.")

    result = read_json(result_file)
    if result_file == error_file:
        message = str(result.get("message", "Unknown service error."))
        raise RuntimeError(message)

    return result


def send_history_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe_remove(HISTORY_RESPONSE_FILE)
    safe_remove(HISTORY_REQUEST_FILE)

    write_json_atomic(HISTORY_REQUEST_FILE, payload)

    result_file = wait_for_file([HISTORY_RESPONSE_FILE])
    if result_file is None:
        raise TimeoutError("Timed out waiting for History / Analytics Tracker response.")

    result = read_json(result_file)
    if result.get("status") != "ok":
        raise RuntimeError(str(result.get("message", "Unknown history service error.")))

    return result


def canonicalize_category(raw_category: str) -> Optional[str]:
    response = send_standard_service_request(
        CATEGORY_REQUEST_FILE,
        CATEGORY_DONE_FILE,
        CATEGORY_ERROR_FILE,
        {
            "action": "canonicalize",
            "category": raw_category,
            "configPath": CATEGORY_CONFIG_FILE
        }
    )
    return response.get("canonicalCategory")


def request_total_summary(expenses_path: str, start_date: str, end_date: str) -> float:
    response = send_standard_service_request(
        SUMMARY_REQUEST_FILE,
        SUMMARY_DONE_FILE,
        SUMMARY_ERROR_FILE,
        {
            "inputJsonPath": expenses_path,
            "action": "total",
            "startDate": start_date,
            "endDate": end_date
        }
    )
    return float(response.get("totalAmount", 0.0))


def request_category_summary(expenses_path: str, start_date: str, end_date: str) -> Dict[str, float]:
    response = send_standard_service_request(
        SUMMARY_REQUEST_FILE,
        SUMMARY_DONE_FILE,
        SUMMARY_ERROR_FILE,
        {
            "inputJsonPath": expenses_path,
            "action": "byCategory",
            "startDate": start_date,
            "endDate": end_date
        }
    )
    data = response.get("categoryTotals", {})
    if not isinstance(data, dict):
        return {}
    out: Dict[str, float] = {}
    for key, value in data.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def request_generate_recurring(target_month: str) -> List[Dict[str, Any]]:
    response = send_standard_service_request(
        RECURRING_REQUEST_FILE,
        RECURRING_DONE_FILE,
        RECURRING_ERROR_FILE,
        {
            "rulesJsonPath": RECURRING_RULES_FILE,
            "existingExpensesPath": DATA_FILE,
            "targetMonth": target_month
        }
    )

    generated = response.get("generatedExpenses", [])
    if not isinstance(generated, list):
        return []
    return [item for item in generated if isinstance(item, dict)]


def log_history_event(event_type: str, payload: Dict[str, Any]) -> None:
    send_history_request(
        {
            "action": "logEvent",
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "source": "budget_app",
            "eventType": event_type,
            "payload": payload
        }
    )


def load_recurring_rules() -> List[Dict[str, Any]]:
    if not os.path.exists(RECURRING_RULES_FILE):
        return []

    try:
        data = read_json(RECURRING_RULES_FILE)
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return []

    rules: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            rules.append(item)
    return rules


def save_recurring_rules(rules: List[Dict[str, Any]]) -> None:
    write_json_atomic(RECURRING_RULES_FILE, rules)


def make_rule_id(name: str, existing_rules: List[Dict[str, Any]]) -> str:
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
    base = "_".join(part for part in base.split("_") if part)
    if not base:
        base = "rule"

    existing_ids = {str(rule.get("ruleId", "")).strip().lower() for rule in existing_rules}

    if base not in existing_ids:
        return base

    counter = 2
    while f"{base}_{counter}" in existing_ids:
        counter += 1
    return f"{base}_{counter}"


class BudgetTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Budget Tracker")
        self.configure(bg=BG)

        ensure_default_category_config()
        ensure_default_recurring_rules()

        if not os.path.exists(DATA_FILE):
            save_expenses([])

        self.geometry("1080x720")
        self.minsize(1080, 720)

        self.expenses = load_expenses()

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.frames = {}
        for FrameCls in (
            MainMenu,
            AddExpense,
            ViewExpenses,
            ViewSpending,
            RecurringExpenses
        ):
            frame = FrameCls(self.container, self)
            self.frames[FrameCls.__name__] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show("MainMenu")

    def show(self, name: str):
        frame = self.frames[name]
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()

    def reload_expenses(self) -> None:
        self.expenses = load_expenses()

    def add_expense(self, amount: float, category: str, extra_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        created_at = datetime.now().isoformat(timespec="seconds")
        entry: Dict[str, Any] = {
            "amount": amount,
            "category": category.strip(),
            "created_at": created_at
        }
        if extra_fields:
            entry.update(extra_fields)

        self.expenses.append(entry)
        save_expenses(self.expenses)
        return entry

    def delete_expense(self, index: int):
        if 0 <= index < len(self.expenses):
            removed = self.expenses.pop(index)
            save_expenses(self.expenses)

            try:
                log_history_event(
                    "expense_deleted",
                    {
                        "amount": removed.get("amount"),
                        "category": removed.get("category"),
                        "created_at": removed.get("created_at")
                    }
                )
            except Exception:
                pass

    def clear_all_expenses(self):
        count = len(self.expenses)
        self.expenses = []
        save_expenses(self.expenses)

        try:
            log_history_event(
                "all_expenses_cleared",
                {
                    "removedCount": count
                }
            )
        except Exception:
            pass

    def import_generated_expenses(self, generated_expenses: List[Dict[str, Any]]) -> int:
        added_count = 0
        for expense in generated_expenses:
            amount = expense.get("amount")
            category = str(expense.get("category", "")).strip()
            created_at = str(expense.get("created_at", "")).strip()

            try:
                amount = float(amount)
            except (TypeError, ValueError):
                continue

            if amount <= 0 or not category or not created_at:
                continue

            entry = dict(expense)
            entry["amount"] = amount
            entry["category"] = category
            entry["created_at"] = created_at
            self.expenses.append(entry)
            added_count += 1

        if added_count > 0:
            save_expenses(self.expenses)

        return added_count


class MainMenu(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        tk.Label(self, text="Budget Tracker - Main Menu", font=("Arial", 18), bg=BG).pack(pady=(36, 22))

        btn_w = 28
        btn_h = 2

        tk.Button(self, text="Add Expense", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("AddExpense")).pack(pady=10)

        tk.Button(self, text="View Expenses", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("ViewExpenses")).pack(pady=10)

        tk.Button(self, text="View Spending", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("ViewSpending")).pack(pady=10)

        tk.Button(self, text="Recurring Expenses", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("RecurringExpenses")).pack(pady=10)

        tk.Button(self, text="Exit", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=app.destroy).pack(pady=10)


class AddExpense(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        self.amount_var = tk.StringVar(value="")
        self.category_var = tk.StringVar(value="")
        self.new_category_var = tk.StringVar(value="")
        self.error_var = tk.StringVar(value="")

        tk.Label(self, text="Add Expense", font=("Arial", 18), bg=BG).pack(pady=(24, 18))

        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=30, pady=10)

        left = tk.Frame(content, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 25))

        right = tk.Frame(content, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        form = tk.Frame(left, bg=BG)
        form.pack(pady=10)

        tk.Label(form, text="Enter Expense Amount:", font=("Arial", 14), bg=BG).grid(row=0, column=0, sticky="e", padx=16, pady=12)
        self.amount_entry = tk.Entry(form, textvariable=self.amount_var, font=("Arial", 14), width=20)
        self.amount_entry.grid(row=0, column=1, sticky="w", padx=16, pady=12)

        tk.Label(form, text="Enter Expense Category:", font=("Arial", 14), bg=BG).grid(row=1, column=0, sticky="e", padx=16, pady=12)
        self.category_entry = tk.Entry(form, textvariable=self.category_var, font=("Arial", 14), width=20)
        self.category_entry.grid(row=1, column=1, sticky="w", padx=16, pady=12)

        self.create_frame = tk.Frame(left, bg=BG)
        tk.Label(self.create_frame, text="New Category Name:", font=("Arial", 13), bg=BG).grid(row=0, column=0, sticky="e", padx=10, pady=8)
        self.new_category_entry = tk.Entry(self.create_frame, textvariable=self.new_category_var, font=("Arial", 13), width=20)
        self.new_category_entry.grid(row=0, column=1, sticky="w", padx=10, pady=8)
        tk.Button(self.create_frame, text="Create Category", font=("Arial", 12), width=16,
                  command=self.create_category_from_prompt).grid(row=1, column=0, padx=10, pady=10)
        tk.Button(self.create_frame, text="Cancel", font=("Arial", 12), width=16,
                  command=self.hide_create_category).grid(row=1, column=1, padx=10, pady=10)

        btns = tk.Frame(left, bg=BG)
        btns.pack(pady=18)

        tk.Button(btns, text="Save Expense", font=("Arial", 14), width=16, height=2,
                  command=self.on_save).grid(row=0, column=0, padx=18)
        tk.Button(btns, text="Back", font=("Arial", 14), width=16, height=2,
                  command=self.on_back).grid(row=0, column=1, padx=18)

        tk.Label(left, textvariable=self.error_var, font=("Arial", 12), bg=BG, fg="#b00020", justify="left").pack(pady=(18, 0))

        tk.Label(right, text="Available Categories", font=("Arial", 14, "bold"), bg=BG).pack(pady=(10, 8))

        list_wrap = tk.Frame(right, bg=BG)
        list_wrap.pack(fill="both", expand=True)

        self.category_listbox = tk.Listbox(list_wrap, font=("Arial", 12), width=30, height=18, exportselection=False)
        self.category_listbox.pack(side="left", fill="both", expand=True)

        sb = tk.Scrollbar(list_wrap, orient="vertical", command=self.category_listbox.yview)
        sb.pack(side="left", fill="y")
        self.category_listbox.config(yscrollcommand=sb.set)

        self.category_listbox.bind("<<ListboxSelect>>", self.use_selected_category)

        tk.Button(right, text="Use Selected Category", font=("Arial", 13), width=22,
                  command=self.use_selected_category).pack(pady=12)

    def on_show(self):
        self.error_var.set("")
        self.hide_create_category()
        self.refresh_category_list()
        self.after(50, self.amount_entry.focus_set)

    def refresh_category_list(self):
        self.category_listbox.delete(0, tk.END)
        for category in get_all_categories():
            self.category_listbox.insert(tk.END, category)

    def use_selected_category(self, event=None):
        selection = self.category_listbox.curselection()
        if not selection:
            return
        chosen = self.category_listbox.get(selection[0])
        self.category_var.set(chosen)

    def show_create_category(self, suggested_name: str = ""):
        self.new_category_var.set(normalize_category_name(suggested_name))
        self.create_frame.pack(pady=(10, 4))
        self.after(50, self.new_category_entry.focus_set)

    def hide_create_category(self):
        self.new_category_var.set("")
        self.create_frame.pack_forget()

    def create_category_from_prompt(self):
        raw_name = self.new_category_var.get().strip()
        if not raw_name:
            self.error_var.set("Please enter a category name to create.")
            return

        try:
            created = add_category_to_config(raw_name)
            self.refresh_category_list()
            self.category_var.set(created)
            self.hide_create_category()
            self.error_var.set(f'Category "{created}" created. You can now save the expense.')
            try:
                log_history_event(
                    "category_created",
                    {
                        "category": created,
                        "sourceScreen": "AddExpense"
                    }
                )
            except Exception:
                pass
        except Exception as exc:
            self.error_var.set(str(exc))

    def on_back(self):
        self.error_var.set("")
        self.hide_create_category()
        self.app.show("MainMenu")

    def on_save(self):
        raw_amount = self.amount_var.get().strip()
        raw_category = self.category_var.get().strip()

        if not raw_amount:
            self.error_var.set("Invalid amount. Please enter a number.")
            return

        try:
            amount = float(raw_amount)
        except ValueError:
            self.error_var.set("Invalid amount. Please enter a number.")
            return

        if amount <= 0:
            self.error_var.set("Invalid amount. Please enter a number greater than 0.")
            return

        if not raw_category:
            self.error_var.set("Invalid category. Please enter a category.")
            return

        try:
            canonical_category = canonicalize_category(raw_category)
        except Exception as exc:
            self.error_var.set(f"Category service error: {exc}")
            return

        if not canonical_category:
            create_new = messagebox.askyesno(
                "Create Category",
                f'"{raw_category}" does not exist.\n\nWould you like to create a new category?'
            )
            if create_new:
                self.show_create_category(raw_category)
                self.error_var.set("Create the new category, then save the expense again.")
            else:
                self.error_var.set("Expense not saved.")
            return

        entry = self.app.add_expense(amount, canonical_category)

        try:
            log_history_event(
                "expense_added",
                {
                    "amount": entry["amount"],
                    "category": entry["category"],
                    "created_at": entry["created_at"]
                }
            )
        except Exception as exc:
            messagebox.showwarning("History service warning", f"Expense saved, but event logging failed:\n{exc}")

        self.error_var.set("")
        messagebox.showinfo("Saved", f"Expense saved under category: {canonical_category}")
        self.amount_var.set("")
        self.category_var.set("")
        self.hide_create_category()
        self.app.show("MainMenu")


class ViewExpenses(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        tk.Label(self, text="Expense List", font=("Arial", 18), bg=BG).pack(pady=(28, 18))

        headers = tk.Frame(self, bg=BG)
        headers.pack()

        tk.Label(headers, text="Date", font=("Arial", 12, "bold"), bg=BG).grid(row=0, column=0, padx=(0, 80))
        tk.Label(headers, text="Amount", font=("Arial", 12, "bold"), bg=BG).grid(row=0, column=1, padx=(0, 80))
        tk.Label(headers, text="Category", font=("Arial", 12, "bold"), bg=BG).grid(row=0, column=2, padx=(0, 80))
        tk.Label(headers, text="Source", font=("Arial", 12, "bold"), bg=BG).grid(row=0, column=3)

        table = tk.Frame(self, bg=BG)
        table.pack(pady=8)

        self.date_list = tk.Listbox(table, font=("Arial", 11), width=16, height=16, bd=1, relief="solid", exportselection=False)
        self.date_list.grid(row=0, column=0, sticky="nsew")

        self.amount_list = tk.Listbox(table, font=("Arial", 11), width=14, height=16, bd=1, relief="solid", exportselection=False)
        self.amount_list.grid(row=0, column=1, sticky="nsew")

        self.category_list = tk.Listbox(table, font=("Arial", 11), width=26, height=16, bd=1, relief="solid", exportselection=False)
        self.category_list.grid(row=0, column=2, sticky="nsew")

        self.source_list = tk.Listbox(table, font=("Arial", 11), width=20, height=16, bd=1, relief="solid", exportselection=False)
        self.source_list.grid(row=0, column=3, sticky="nsew")

        sb = tk.Scrollbar(table, orient="vertical")
        sb.grid(row=0, column=4, sticky="ns")

        self.date_list.config(yscrollcommand=sb.set)
        self.amount_list.config(yscrollcommand=sb.set)
        self.category_list.config(yscrollcommand=sb.set)
        self.source_list.config(yscrollcommand=sb.set)
        sb.config(command=self._scroll_both)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=18)

        tk.Button(
            btn_frame,
            text="Delete Selected Expense",
            font=("Arial", 13),
            width=22,
            command=self.delete_selected
        ).grid(row=0, column=0, padx=12)

        tk.Button(
            btn_frame,
            text="Clear ALL Expenses",
            font=("Arial", 13),
            width=22,
            command=self.clear_all
        ).grid(row=0, column=1, padx=12)

        tk.Button(
            btn_frame,
            text="Back",
            font=("Arial", 13),
            width=16,
            command=lambda: app.show("MainMenu")
        ).grid(row=0, column=2, padx=12)

        self.date_list.bind("<MouseWheel>", self._wheel)
        self.amount_list.bind("<MouseWheel>", self._wheel)
        self.category_list.bind("<MouseWheel>", self._wheel)
        self.source_list.bind("<MouseWheel>", self._wheel)

        self.date_list.bind("<<ListboxSelect>>", self.sync_selection)
        self.amount_list.bind("<<ListboxSelect>>", self.sync_selection)
        self.category_list.bind("<<ListboxSelect>>", self.sync_selection)
        self.source_list.bind("<<ListboxSelect>>", self.sync_selection)

    def _scroll_both(self, *args):
        self.date_list.yview(*args)
        self.amount_list.yview(*args)
        self.category_list.yview(*args)
        self.source_list.yview(*args)

    def _wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self.date_list.yview_scroll(delta, "units")
        self.amount_list.yview_scroll(delta, "units")
        self.category_list.yview_scroll(delta, "units")
        self.source_list.yview_scroll(delta, "units")
        return "break"

    def sync_selection(self, event=None):
        widgets = [self.date_list, self.amount_list, self.category_list, self.source_list]
        index = None
        for widget in widgets:
            selection = widget.curselection()
            if selection:
                index = selection[0]
                break

        if index is None:
            return

        for widget in widgets:
            widget.selection_clear(0, tk.END)
            widget.selection_set(index)

    def get_selected_index(self):
        selection = self.amount_list.curselection()
        if not selection:
            return None
        return selection[0]

    def delete_selected(self):
        index = self.get_selected_index()

        if index is None:
            messagebox.showwarning("No Selection", "Please select an expense to delete.")
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            "Delete the selected expense?"
        )

        if not confirm:
            return

        self.app.delete_expense(index)
        self.on_show()

    def clear_all(self):
        if not self.app.expenses:
            messagebox.showinfo("Nothing to Clear", "No expenses exist.")
            return

        confirm = messagebox.askyesno(
            "Confirm Clear All",
            "This will permanently delete ALL expenses.\n\nContinue?"
        )

        if not confirm:
            return

        self.app.clear_all_expenses()
        self.on_show()

    def on_show(self):
        self.app.reload_expenses()

        self.date_list.delete(0, tk.END)
        self.amount_list.delete(0, tk.END)
        self.category_list.delete(0, tk.END)
        self.source_list.delete(0, tk.END)

        if not self.app.expenses:
            self.date_list.insert(tk.END, "")
            self.amount_list.insert(tk.END, "")
            self.category_list.insert(tk.END, "No expenses yet.")
            self.source_list.insert(tk.END, "")
            return

        for e in self.app.expenses:
            try:
                amt = float(e.get("amount", 0.0))
            except (TypeError, ValueError):
                continue

            cat = str(e.get("category", "")).strip()
            created_at = str(e.get("created_at", "")).strip()
            source = "Recurring" if e.get("recurringGenerated") else "Manual"

            display_date = created_at[:10] if created_at else ""
            self.date_list.insert(tk.END, display_date)
            self.amount_list.insert(tk.END, f"${amt:,.2f}")
            self.category_list.insert(tk.END, cat)
            self.source_list.insert(tk.END, source)


class ViewSpending(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        self.range_var = tk.StringVar(value="")
        self.all_total_var = tk.StringVar(value="$0.00")
        self.month_total_var = tk.StringVar(value="$0.00")
        self.year_total_var = tk.StringVar(value="$0.00")
        self.category_status_var = tk.StringVar(value="")
        self.new_category_var = tk.StringVar(value="")
        self.selected_category_var = tk.StringVar(value="")
        self.rename_category_var = tk.StringVar(value="")

        # ---------- OUTER WRAPPER ----------
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)

        content = tk.Frame(outer, bg=BG)
        content.place(relx=0.5, rely=0.5, anchor="center")

        # ---------- TITLE ----------
        tk.Label(
            content,
            text="View Spending",
            font=("Arial", 20, "bold"),
            bg=BG
        ).pack(pady=(0, 18))

        # ---------- SUMMARY CARD ----------
        summary_card = tk.Frame(content, bg="white", bd=1, relief="solid", padx=24, pady=18)
        summary_card.pack(fill="x", pady=(0, 18))

        summary_grid = tk.Frame(summary_card, bg="white")
        summary_grid.pack()

        tk.Label(summary_grid, text="All Time Total", font=("Arial", 12, "bold"), bg="white").grid(row=0, column=0, padx=30, pady=(0, 4))
        tk.Label(summary_grid, text="This Month", font=("Arial", 12, "bold"), bg="white").grid(row=0, column=1, padx=30, pady=(0, 4))
        tk.Label(summary_grid, text="This Year", font=("Arial", 12, "bold"), bg="white").grid(row=0, column=2, padx=30, pady=(0, 4))

        tk.Label(summary_grid, textvariable=self.all_total_var, font=("Arial", 16), bg="white").grid(row=1, column=0, padx=30, pady=(0, 2))
        tk.Label(summary_grid, textvariable=self.month_total_var, font=("Arial", 16), bg="white").grid(row=1, column=1, padx=30, pady=(0, 2))
        tk.Label(summary_grid, textvariable=self.year_total_var, font=("Arial", 16), bg="white").grid(row=1, column=2, padx=30, pady=(0, 2))

        tk.Label(
            summary_card,
            textvariable=self.range_var,
            font=("Arial", 10),
            bg="white"
        ).pack(pady=(12, 0))

        # ---------- MAIN TWO-COLUMN AREA ----------
        middle = tk.Frame(content, bg=BG)
        middle.pack()

        # LEFT PANEL
        left_panel = tk.Frame(middle, bg="white", bd=1, relief="solid", padx=20, pady=18)
        left_panel.grid(row=0, column=0, padx=(0, 18), sticky="n")

        tk.Label(
            left_panel,
            text="Spending By Category",
            font=("Arial", 15, "bold"),
            bg="white"
        ).pack(pady=(0, 12))

        headers = tk.Frame(left_panel, bg="white")
        headers.pack()

        tk.Label(headers, text="Category", font=("Arial", 12, "bold"), bg="white", width=20, anchor="w").grid(row=0, column=0, padx=(0, 8))
        tk.Label(headers, text="Total", font=("Arial", 12, "bold"), bg="white", width=12, anchor="w").grid(row=0, column=1)

        table = tk.Frame(left_panel, bg="white")
        table.pack(pady=(8, 0))

        self.category_list = tk.Listbox(
            table,
            font=("Arial", 11),
            width=24,
            height=16,
            bd=1,
            relief="solid",
            exportselection=False
        )
        self.category_list.grid(row=0, column=0, sticky="nsew")

        self.total_list = tk.Listbox(
            table,
            font=("Arial", 11),
            width=14,
            height=16,
            bd=1,
            relief="solid",
            exportselection=False
        )
        self.total_list.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        sb = tk.Scrollbar(table, orient="vertical")
        sb.grid(row=0, column=2, sticky="ns", padx=(6, 0))

        self.category_list.config(yscrollcommand=sb.set)
        self.total_list.config(yscrollcommand=sb.set)
        sb.config(command=self._scroll_both)

        self.category_list.bind("<MouseWheel>", self._wheel)
        self.total_list.bind("<MouseWheel>", self._wheel)
        self.category_list.bind("<<ListboxSelect>>", self.sync_selection)
        self.total_list.bind("<<ListboxSelect>>", self.sync_selection)

        # RIGHT PANEL
        right_panel = tk.Frame(middle, bg="white", bd=1, relief="solid", padx=20, pady=18)
        right_panel.grid(row=0, column=1, sticky="n")

        tk.Label(
            right_panel,
            text="Manage Categories",
            font=("Arial", 15, "bold"),
            bg="white"
        ).pack(pady=(0, 12))

        list_wrap = tk.Frame(right_panel, bg="white")
        list_wrap.pack()

        self.all_categories_listbox = tk.Listbox(
            list_wrap,
            font=("Arial", 11),
            width=24,
            height=10,
            exportselection=False,
            bd=1,
            relief="solid"
        )
        self.all_categories_listbox.pack(side="left")

        cat_sb = tk.Scrollbar(list_wrap, orient="vertical", command=self.all_categories_listbox.yview)
        cat_sb.pack(side="left", fill="y", padx=(6, 0))

        self.all_categories_listbox.config(yscrollcommand=cat_sb.set)
        self.all_categories_listbox.bind("<<ListboxSelect>>", self.on_category_select)

        create_box = tk.Frame(right_panel, bg="white")
        create_box.pack(fill="x", pady=(16, 10))

        tk.Label(create_box, text="New Category Name", font=("Arial", 11, "bold"), bg="white").pack(anchor="w", pady=(0, 5))
        tk.Entry(create_box, textvariable=self.new_category_var, font=("Arial", 11), width=24).pack(anchor="w")
        tk.Button(
            create_box,
            text="Create Category",
            font=("Arial", 11),
            width=18,
            command=self.create_category
        ).pack(anchor="w", pady=(8, 0))

        edit_box = tk.Frame(right_panel, bg="white")
        edit_box.pack(fill="x", pady=(6, 0))

        tk.Label(edit_box, text="Selected Category", font=("Arial", 11, "bold"), bg="white").pack(anchor="w", pady=(0, 4))
        tk.Label(edit_box, textvariable=self.selected_category_var, font=("Arial", 11), bg="white").pack(anchor="w", pady=(0, 10))

        tk.Label(edit_box, text="Rename Selected To", font=("Arial", 11, "bold"), bg="white").pack(anchor="w", pady=(0, 5))
        tk.Entry(edit_box, textvariable=self.rename_category_var, font=("Arial", 11), width=24).pack(anchor="w")

        action_row = tk.Frame(edit_box, bg="white")
        action_row.pack(anchor="w", pady=(10, 0))

        tk.Button(
            action_row,
            text="Update",
            font=("Arial", 11),
            width=10,
            command=self.update_category
        ).grid(row=0, column=0, padx=(0, 8))

        tk.Button(
            action_row,
            text="Delete",
            font=("Arial", 11),
            width=10,
            command=self.delete_category
        ).grid(row=0, column=1)

        tk.Label(
            right_panel,
            textvariable=self.category_status_var,
            font=("Arial", 10),
            bg="white",
            fg="#b00020",
            justify="left",
            wraplength=240
        ).pack(pady=(14, 0), anchor="w")

        # ---------- BACK BUTTON ----------
        bottom = tk.Frame(content, bg=BG)
        bottom.pack(pady=(18, 0))

        tk.Button(
            bottom,
            text="Back",
            font=("Arial", 13),
            width=16,
            height=2,
            command=lambda: app.show("MainMenu")
        ).pack()

    def _scroll_both(self, *args):
        self.category_list.yview(*args)
        self.total_list.yview(*args)

    def _wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self.category_list.yview_scroll(delta, "units")
        self.total_list.yview_scroll(delta, "units")
        return "break"

    def sync_selection(self, event=None):
        index = None
        if self.category_list.curselection():
            index = self.category_list.curselection()[0]
        elif self.total_list.curselection():
            index = self.total_list.curselection()[0]

        if index is None:
            return

        self.category_list.selection_clear(0, tk.END)
        self.total_list.selection_clear(0, tk.END)
        self.category_list.selection_set(index)
        self.total_list.selection_set(index)

    def refresh_categories_panel(self):
        self.all_categories_listbox.delete(0, tk.END)
        for category in get_all_categories():
            self.all_categories_listbox.insert(tk.END, category)

    def on_category_select(self, event=None):
        selection = self.all_categories_listbox.curselection()
        if not selection:
            return
        category = self.all_categories_listbox.get(selection[0])
        self.selected_category_var.set(category)
        self.rename_category_var.set(category)

    def create_category(self):
        raw_name = self.new_category_var.get().strip()
        if not raw_name:
            self.category_status_var.set("Please enter a category name.")
            return

        try:
            created = add_category_to_config(raw_name)
            self.new_category_var.set("")
            self.selected_category_var.set(created)
            self.rename_category_var.set(created)
            self.category_status_var.set(f'Category "{created}" created.')
            self.refresh_categories_panel()
            try:
                log_history_event(
                    "category_created",
                    {
                        "category": created,
                        "sourceScreen": "ViewSpending"
                    }
                )
            except Exception:
                pass
        except Exception as exc:
            self.category_status_var.set(str(exc))

    def update_category(self):
        old_name = self.selected_category_var.get().strip()
        new_name = self.rename_category_var.get().strip()

        if not old_name:
            self.category_status_var.set("Select a category to update.")
            return

        try:
            updated = update_category_in_config(old_name, new_name)
            self.selected_category_var.set(updated)
            self.rename_category_var.set(updated)
            self.category_status_var.set(f'Category updated to "{updated}".')
            self.refresh_categories_panel()
            self.on_show()
            try:
                log_history_event(
                    "category_updated",
                    {
                        "oldCategory": old_name,
                        "newCategory": updated,
                        "sourceScreen": "ViewSpending"
                    }
                )
            except Exception:
                pass
        except Exception as exc:
            self.category_status_var.set(str(exc))

    def delete_category(self):
        category = self.selected_category_var.get().strip()
        if not category:
            self.category_status_var.set("Select a category to delete.")
            return

        confirm = messagebox.askyesno(
            "Delete Category",
            f'Delete category "{category}"?\n\nExpenses and recurring rules using it will be moved to "Other".'
        )
        if not confirm:
            return

        try:
            delete_category_from_config(category)
            self.selected_category_var.set("")
            self.rename_category_var.set("")
            self.category_status_var.set(f'Category "{category}" deleted. Matching items were moved to "Other".')
            self.refresh_categories_panel()
            self.on_show()
            try:
                log_history_event(
                    "category_deleted",
                    {
                        "category": category,
                        "replacementCategory": "Other",
                        "sourceScreen": "ViewSpending"
                    }
                )
            except Exception:
                pass
        except Exception as exc:
            self.category_status_var.set(str(exc))

    def on_show(self):
        self.app.reload_expenses()
        self.refresh_categories_panel()

        self.category_list.delete(0, tk.END)
        self.total_list.delete(0, tk.END)

        today = date.today()
        all_start, all_end = get_date_bounds(self.app.expenses)
        month_start, month_end = get_month_bounds(today)
        year_start, year_end = get_year_bounds(today)

        month_total = None
        year_total = None

        try:
            all_total = request_total_summary(DATA_FILE, all_start, all_end)
            self.all_total_var.set(f"${all_total:,.2f}")
        except Exception as exc:
            self.all_total_var.set("Unavailable")
            self.range_var.set(f"Summary error: {exc}")
            return

        try:
            month_total = request_total_summary(DATA_FILE, month_start, month_end)
            self.month_total_var.set(f"${month_total:,.2f}")
        except Exception:
            self.month_total_var.set("Unavailable")

        try:
            year_total = request_total_summary(DATA_FILE, year_start, year_end)
            self.year_total_var.set(f"${year_total:,.2f}")
        except Exception:
            self.year_total_var.set("Unavailable")

        try:
            category_totals = request_category_summary(DATA_FILE, all_start, all_end)
            self.range_var.set(f"Category totals range: {all_start} to {all_end}")

            if not category_totals:
                self.category_list.insert(tk.END, "No data")
                self.total_list.insert(tk.END, "$0.00")
            else:
                for category, total in category_totals.items():
                    self.category_list.insert(tk.END, category)
                    self.total_list.insert(tk.END, f"${total:,.2f}")

            try:
                log_history_event(
                    "view_spending_summary",
                    {
                        "startDate": all_start,
                        "endDate": all_end,
                        "allTimeTotal": all_total,
                        "monthTotal": month_total,
                        "yearTotal": year_total,
                        "categoryCount": len(category_totals)
                    }
                )
            except Exception:
                pass
        except Exception as exc:
            self.category_list.insert(tk.END, "Service error")
            self.total_list.insert(tk.END, "")
            self.range_var.set(f"Summary error: {exc}")


class RecurringExpenses(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        self.name_var = tk.StringVar(value="")
        self.amount_var = tk.StringVar(value="")
        self.category_var = tk.StringVar(value="")
        self.day_var = tk.StringVar(value="")
        self.description_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.selected_index = None

        tk.Label(self, text="Recurring Expenses", font=("Arial", 18), bg=BG).pack(pady=(20, 14))

        form = tk.Frame(self, bg=BG)
        form.pack(pady=8)

        tk.Label(form, text="Name:", font=("Arial", 12), bg=BG).grid(row=0, column=0, sticky="e", padx=10, pady=8)
        tk.Entry(form, textvariable=self.name_var, font=("Arial", 12), width=24).grid(row=0, column=1, sticky="w", padx=10, pady=8)

        tk.Label(form, text="Amount:", font=("Arial", 12), bg=BG).grid(row=1, column=0, sticky="e", padx=10, pady=8)
        tk.Entry(form, textvariable=self.amount_var, font=("Arial", 12), width=24).grid(row=1, column=1, sticky="w", padx=10, pady=8)

        tk.Label(form, text="Category:", font=("Arial", 12), bg=BG).grid(row=2, column=0, sticky="e", padx=10, pady=8)
        tk.Entry(form, textvariable=self.category_var, font=("Arial", 12), width=24).grid(row=2, column=1, sticky="w", padx=10, pady=8)

        tk.Label(form, text="Day of Month:", font=("Arial", 12), bg=BG).grid(row=3, column=0, sticky="e", padx=10, pady=8)
        tk.Entry(form, textvariable=self.day_var, font=("Arial", 12), width=24).grid(row=3, column=1, sticky="w", padx=10, pady=8)

        tk.Label(form, text="Description:", font=("Arial", 12), bg=BG).grid(row=4, column=0, sticky="e", padx=10, pady=8)
        tk.Entry(form, textvariable=self.description_var, font=("Arial", 12), width=24).grid(row=4, column=1, sticky="w", padx=10, pady=8)

        btns = tk.Frame(self, bg=BG)
        btns.pack(pady=12)

        tk.Button(btns, text="Add", font=("Arial", 12), width=12, command=self.add_rule).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="Update", font=("Arial", 12), width=12, command=self.update_rule).grid(row=0, column=1, padx=6)
        tk.Button(btns, text="Delete", font=("Arial", 12), width=12, command=self.delete_rule).grid(row=0, column=2, padx=6)
        tk.Button(btns, text="Clear Form", font=("Arial", 12), width=12, command=self.clear_form).grid(row=0, column=3, padx=6)
        tk.Button(btns, text="Back", font=("Arial", 12), width=12, command=lambda: app.show("MainMenu")).grid(row=0, column=4, padx=6)

        tk.Label(self, textvariable=self.status_var, font=("Arial", 11), bg=BG, fg="#b00020").pack(pady=(4, 8))

        headers = tk.Frame(self, bg=BG)
        headers.pack()

        tk.Label(headers, text="Rule ID", font=("Arial", 11, "bold"), bg=BG).grid(row=0, column=0, padx=(0, 30))
        tk.Label(headers, text="Amount", font=("Arial", 11, "bold"), bg=BG).grid(row=0, column=1, padx=(0, 30))
        tk.Label(headers, text="Category", font=("Arial", 11, "bold"), bg=BG).grid(row=0, column=2, padx=(0, 30))
        tk.Label(headers, text="Day", font=("Arial", 11, "bold"), bg=BG).grid(row=0, column=3, padx=(0, 30))
        tk.Label(headers, text="Description", font=("Arial", 11, "bold"), bg=BG).grid(row=0, column=4)

        table = tk.Frame(self, bg=BG)
        table.pack(pady=6)

        self.rule_list = tk.Listbox(table, font=("Arial", 11), width=20, height=10, exportselection=False)
        self.rule_list.grid(row=0, column=0)

        self.amount_list = tk.Listbox(table, font=("Arial", 11), width=12, height=10, exportselection=False)
        self.amount_list.grid(row=0, column=1)

        self.category_list = tk.Listbox(table, font=("Arial", 11), width=16, height=10, exportselection=False)
        self.category_list.grid(row=0, column=2)

        self.day_list = tk.Listbox(table, font=("Arial", 11), width=8, height=10, exportselection=False)
        self.day_list.grid(row=0, column=3)

        self.description_list = tk.Listbox(table, font=("Arial", 11), width=28, height=10, exportselection=False)
        self.description_list.grid(row=0, column=4)

        sb = tk.Scrollbar(table, orient="vertical")
        sb.grid(row=0, column=5, sticky="ns")

        self.rule_list.config(yscrollcommand=sb.set)
        self.amount_list.config(yscrollcommand=sb.set)
        self.category_list.config(yscrollcommand=sb.set)
        self.day_list.config(yscrollcommand=sb.set)
        self.description_list.config(yscrollcommand=sb.set)
        sb.config(command=self._scroll_both)

        self.rule_list.bind("<<ListboxSelect>>", self.on_select)
        self.amount_list.bind("<<ListboxSelect>>", self.on_select)
        self.category_list.bind("<<ListboxSelect>>", self.on_select)
        self.day_list.bind("<<ListboxSelect>>", self.on_select)
        self.description_list.bind("<<ListboxSelect>>", self.on_select)

    def _scroll_both(self, *args):
        self.rule_list.yview(*args)
        self.amount_list.yview(*args)
        self.category_list.yview(*args)
        self.day_list.yview(*args)
        self.description_list.yview(*args)

    def on_show(self):
        self.refresh_rules()
        self.clear_form()

    def refresh_rules(self):
        self.rule_list.delete(0, tk.END)
        self.amount_list.delete(0, tk.END)
        self.category_list.delete(0, tk.END)
        self.day_list.delete(0, tk.END)
        self.description_list.delete(0, tk.END)

        rules = load_recurring_rules()
        if not rules:
            self.rule_list.insert(tk.END, "No recurring expenses yet")
            self.amount_list.insert(tk.END, "")
            self.category_list.insert(tk.END, "")
            self.day_list.insert(tk.END, "")
            self.description_list.insert(tk.END, "")
            return

        for rule in rules:
            self.rule_list.insert(tk.END, str(rule.get("ruleId", "")))
            self.amount_list.insert(tk.END, f"${float(rule.get('amount', 0.0)):,.2f}")
            self.category_list.insert(tk.END, str(rule.get("category", "")))
            self.day_list.insert(tk.END, str(rule.get("dayOfMonth", "")))
            self.description_list.insert(tk.END, str(rule.get("description", "")))

    def clear_form(self):
        self.name_var.set("")
        self.amount_var.set("")
        self.category_var.set("")
        self.day_var.set("")
        self.description_var.set("")
        self.selected_index = None
        self.status_var.set("")

    def get_rules(self):
        return load_recurring_rules()

    def get_selected_index(self):
        selection = self.rule_list.curselection()
        if not selection:
            return None
        return selection[0]

    def on_select(self, event=None):
        index = self.get_selected_index()
        rules = self.get_rules()

        if index is None or index >= len(rules):
            return

        rule = rules[index]
        self.selected_index = index
        self.name_var.set(str(rule.get("ruleId", "")))
        self.amount_var.set(str(rule.get("amount", "")))
        self.category_var.set(str(rule.get("category", "")))
        self.day_var.set(str(rule.get("dayOfMonth", "")))
        self.description_var.set(str(rule.get("description", "")))

    def validate_form(self):
        name = self.name_var.get().strip()
        raw_amount = self.amount_var.get().strip()
        raw_category = self.category_var.get().strip()
        raw_day = self.day_var.get().strip()
        description = self.description_var.get().strip()

        if not name:
            raise ValueError("Please enter a name.")

        try:
            amount = float(raw_amount)
        except ValueError:
            raise ValueError("Amount must be a number.")

        if amount <= 0:
            raise ValueError("Amount must be greater than 0.")

        if not raw_category:
            raise ValueError("Please enter a category.")

        try:
            day_of_month = int(raw_day)
        except ValueError:
            raise ValueError("Day of month must be an integer.")

        if day_of_month < 1 or day_of_month > 31:
            raise ValueError("Day of month must be between 1 and 31.")

        canonical_category = canonicalize_category(raw_category)
        if not canonical_category:
            raise ValueError("Use an existing category or create one on the View Spending screen.")

        return {
            "ruleId": name,
            "amount": round(amount, 2),
            "category": canonical_category,
            "dayOfMonth": day_of_month,
            "description": description
        }

    def add_rule(self):
        try:
            new_rule = self.validate_form()
        except Exception as exc:
            self.status_var.set(str(exc))
            return

        rules = self.get_rules()
        existing_ids = {str(rule.get("ruleId", "")).strip().lower() for rule in rules}
        if new_rule["ruleId"].strip().lower() in existing_ids:
            self.status_var.set("A recurring expense with that name already exists.")
            return

        rules.append(new_rule)
        save_recurring_rules(rules)
        self.refresh_rules()
        self.clear_form()
        self.status_var.set("Recurring expense added.")

    def update_rule(self):
        index = self.selected_index
        rules = self.get_rules()

        if index is None or index >= len(rules):
            self.status_var.set("Select a recurring expense to update.")
            return

        try:
            updated_rule = self.validate_form()
        except Exception as exc:
            self.status_var.set(str(exc))
            return

        for i, rule in enumerate(rules):
            if i != index and str(rule.get("ruleId", "")).strip().lower() == updated_rule["ruleId"].strip().lower():
                self.status_var.set("Another recurring expense already uses that name.")
                return

        rules[index] = updated_rule
        save_recurring_rules(rules)
        self.refresh_rules()
        self.clear_form()
        self.status_var.set("Recurring expense updated.")

    def delete_rule(self):
        index = self.selected_index
        rules = self.get_rules()

        if index is None or index >= len(rules):
            self.status_var.set("Select a recurring expense to delete.")
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            "Delete the selected recurring expense?"
        )
        if not confirm:
            return

        rules.pop(index)
        save_recurring_rules(rules)
        self.refresh_rules()
        self.clear_form()
        self.status_var.set("Recurring expense deleted.")


if __name__ == "__main__":
    BudgetTrackerApp().mainloop()