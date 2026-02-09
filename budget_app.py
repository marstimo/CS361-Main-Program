import json
import os
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

DATA_FILE = "expenses.json"
BG = "#f1f1f1"

def load_expenses():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                amt = float(item.get("amount"))
                cat = str(item.get("category", "")).strip()
                ts = str(item.get("created_at", "")).strip()
                if amt > 0 and cat and ts:
                    out.append({"amount": amt, "category": cat, "created_at": ts})
            except (TypeError, ValueError):
                continue
        return out
    except (OSError, json.JSONDecodeError):
        return []


def save_expenses(expenses):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(expenses, f, indent=2)
    except OSError:
        messagebox.showwarning("Save failed", "Could not save expenses to disk.")


class BudgetTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Budget Tracker")
        self.configure(bg=BG)

        self.geometry("900x520")
        self.minsize(900, 520)

        self.expenses = load_expenses()

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.frames = {}
        for FrameCls in (MainMenu, AddExpense, ViewExpenses, ViewTotal):
            frame = FrameCls(self.container, self)
            self.frames[FrameCls.__name__] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show("MainMenu")

    def show(self, name: str):
        frame = self.frames[name]
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()

    def add_expense(self, amount: float, category: str):
        created_at = datetime.now().isoformat(timespec="seconds")
        self.expenses.append({"amount": amount, "category": category.strip(), "created_at": created_at})
        save_expenses(self.expenses)

    def total_spending(self) -> float:
        total = 0.0
        for e in self.expenses:
            try:
                total += float(e.get("amount", 0.0))
            except (TypeError, ValueError):
                continue
        return total


class MainMenu(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        tk.Label(self, text="Budget Tracker - Main Menu", font=("Arial", 18), bg=BG).pack(pady=(42, 26))

        btn_w = 28
        btn_h = 2

        tk.Button(self, text="Add Expense", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("AddExpense")).pack(pady=10)

        tk.Button(self, text="View Expenses", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("ViewExpenses")).pack(pady=10)

        tk.Button(self, text="View Total Spending", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=lambda: app.show("ViewTotal")).pack(pady=10)

        tk.Button(self, text="Exit", font=("Arial", 14), width=btn_w, height=btn_h,
                  command=app.destroy).pack(pady=10)


class AddExpense(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        self.amount_var = tk.StringVar(value="")
        self.category_var = tk.StringVar(value="")
        self.error_var = tk.StringVar(value="")

        tk.Label(self, text="Add Expense", font=("Arial", 18), bg=BG).pack(pady=(42, 26))

        form = tk.Frame(self, bg=BG)
        form.pack(pady=10)

        tk.Label(form, text="Enter Expense Amount:", font=("Arial", 14), bg=BG).grid(row=0, column=0, sticky="e", padx=16, pady=12)
        self.amount_entry = tk.Entry(form, textvariable=self.amount_var, font=("Arial", 14), width=20)
        self.amount_entry.grid(row=0, column=1, sticky="w", padx=16, pady=12)

        tk.Label(form, text="Enter Expense Category:", font=("Arial", 14), bg=BG).grid(row=1, column=0, sticky="e", padx=16, pady=12)
        self.category_entry = tk.Entry(form, textvariable=self.category_var, font=("Arial", 14), width=20)
        self.category_entry.grid(row=1, column=1, sticky="w", padx=16, pady=12)

        btns = tk.Frame(self, bg=BG)
        btns.pack(pady=18)

        tk.Button(btns, text="Save Expense", font=("Arial", 14), width=16, height=2,
                  command=self.on_save).grid(row=0, column=0, padx=18)
        tk.Button(btns, text="Back", font=("Arial", 14), width=16, height=2,
                  command=self.on_back).grid(row=0, column=1, padx=18)

        tk.Label(self, textvariable=self.error_var, font=("Arial", 12), bg=BG, fg="#b00020").pack(pady=(18, 0))

    def on_show(self):
        self.error_var.set("")
        self.after(50, self.amount_entry.focus_set)

    def on_back(self):
        self.error_var.set("")
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

        self.app.add_expense(amount, raw_category)
        self.error_var.set("")
        messagebox.showinfo("Saved", "Expense saved.")
        self.amount_var.set("")
        self.category_var.set("")
        self.app.show("MainMenu")


class ViewExpenses(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        tk.Label(self, text="Expense List", font=("Arial", 18), bg=BG).pack(pady=(42, 18))

        headers = tk.Frame(self, bg=BG)
        headers.pack()

        tk.Label(headers, text="Amount", font=("Arial", 12, "bold"), bg=BG).grid(row=0, column=0, padx=(0, 220))
        tk.Label(headers, text="Category", font=("Arial", 12, "bold"), bg=BG).grid(row=0, column=1)

        table = tk.Frame(self, bg=BG)
        table.pack(pady=8)

        self.amount_list = tk.Listbox(table, font=("Arial", 12), width=12, height=10, bd=1, relief="solid")
        self.amount_list.grid(row=0, column=0, sticky="nsew")

        self.category_list = tk.Listbox(table, font=("Arial", 12), width=36, height=10, bd=1, relief="solid")
        self.category_list.grid(row=0, column=1, sticky="nsew")

        sb = tk.Scrollbar(table, orient="vertical")
        sb.grid(row=0, column=2, sticky="ns")

        self.amount_list.config(yscrollcommand=sb.set)
        self.category_list.config(yscrollcommand=sb.set)
        sb.config(command=self._scroll_both)

        tk.Button(self, text="Back", font=("Arial", 14), width=16, height=2,
                  command=lambda: app.show("MainMenu")).pack(pady=22)

        self.amount_list.bind("<MouseWheel>", self._wheel)
        self.category_list.bind("<MouseWheel>", self._wheel)

    def _scroll_both(self, *args):
        self.amount_list.yview(*args)
        self.category_list.yview(*args)

    def _wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self.amount_list.yview_scroll(delta, "units")
        self.category_list.yview_scroll(delta, "units")
        return "break"

    def on_show(self):
        self.amount_list.delete(0, tk.END)
        self.category_list.delete(0, tk.END)

        if not self.app.expenses:
            self.amount_list.insert(tk.END, "")
            self.category_list.insert(tk.END, "No expenses yet.")
            return

        for e in self.app.expenses:
            try:
                amt = float(e.get("amount", 0.0))
            except (TypeError, ValueError):
                continue
            cat = str(e.get("category", "")).strip()
            self.amount_list.insert(tk.END, f"${amt:,.2f}")
            self.category_list.insert(tk.END, cat)


class ViewTotal(tk.Frame):
    def __init__(self, parent, app: BudgetTrackerApp):
        super().__init__(parent, bg=BG)
        self.app = app

        tk.Label(self, text="Total Spending", font=("Arial", 18), bg=BG).pack(pady=(60, 40))

        row = tk.Frame(self, bg=BG)
        row.pack()

        tk.Label(row, text="Amount:", font=("Arial", 14), bg=BG).pack(side="left", padx=(0, 18))
        self.total_var = tk.StringVar(value="$0.00")
        tk.Label(row, textvariable=self.total_var, font=("Arial", 14), bg=BG).pack(side="left")

        tk.Button(self, text="Back", font=("Arial", 14), width=16, height=2,
                  command=lambda: app.show("MainMenu")).pack(pady=42)

    def on_show(self):
        self.total_var.set(f"${self.app.total_spending():,.2f}")


if __name__ == "__main__":
    BudgetTrackerApp().mainloop()
