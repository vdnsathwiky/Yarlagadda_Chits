# Yarlagadda Chits

A family-use chit management application built with React + Vite, Python Flask and MongoDB.

## Features
- Separate sign-in accounts and private chit workspaces for family members.
- Four preset schemes using the exact monthly premium, payable amount and dividend schedules transcribed from the supplied sheets:
  - ₹1,00,000 / 10 months / 10 members
  - ₹2,00,000 / 16 months / 16 members
  - ₹1,00,000 / 16 months / 16 members
  - ₹5,00,000 / 20 months / 20 members
- Independent collected and outstanding totals for every chit and every member.
- Partial payments with unpaid balances carried into the next month's amount due.
- Start date accepts today or a future date only. The final due date is calculated automatically from the duration (for example, 5 Dec 2026 + 10 months gives a final due date of 5 Sep 2027).
- Current and upcoming months appear in the normal schedule. Past due months move to History and remain stored for reference.
- Payments cannot be entered against a completed/past month. Carried unpaid balances remain included in the member's current balance.
- Manual one-time monthly allotment: conduct the lottery outside the website, then assign each member to exactly one month and finalise the complete schedule. The app does not draw winners.
- Finalised allotments are read-only and member additions/removals are locked to protect the result.
- The allotment appears in both the schedule and History, alongside the member name and optional ticket/slip number.

## Requirements
- Python 3.10+
- Node.js 18+
- MongoDB Atlas or MongoDB Community Server

## Windows PowerShell setup

### 1. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then set your own MongoDB connection URI and a long random JWT secret. Never commit `.env` to GitHub.

```env
MONGO_URI=mongodb+srv://USERNAME:PASSWORD@YOUR_EXACT_ATLAS_HOST/
MONGO_DB_NAME=yarlagadda_chits_test
JWT_SECRET_KEY=PASTE_A_LONG_RANDOM_SECRET_HERE
FLASK_ENV=development
```

Start Flask:

```powershell
python app.py
```

Backend: `http://127.0.0.1:5000`

### 2. Frontend (second terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## First use
1. Register your account. Your father or other family members can register their own accounts with separate emails.
2. Create a preset chit and choose a start date that is today or later.
3. Add the members. For the four preset chits, the member capacity equals the number of months.
4. Record payments from each member's own card. Every chit and member has a separate ledger.
5. Conduct your lottery physically/outside the website. In the chit, open **Monthly allotment**, select one unique member for every month, optionally enter the paper slip/ticket number, then click **Finalise all allotments**. This is a one-time action. The website does not randomly choose winners.

## Payment calculation
For each member and month:
- Monthly premium comes from the selected scheme's actual month-wise schedule.
- Previous due is the unpaid balance carried forward from earlier months.
- Amount due = this month's premium + previous due.
- Balance = max(0, amount due - payments recorded for this month).
- Multiple partial payments can be recorded. The remaining balance carries into the next month's amount due.
- The member's total collected and outstanding are shown separately. Outstanding dues are calculated only through instalments due on or before today; later instalments are shown separately and are not counted as current dues. Chit-level totals are only the sum of that chit; they are never mixed with another chit.

## Schedule and History
- The schedule dates are generated monthly from the chosen start date and the selected duration.
- The end date is the due date of the final month. Example: start 5 Dec 2026, 10 months → last due date 5 Sep 2027.
- Months with due dates before today are hidden from the current schedule and appear in History.
- Historical records are not deleted. Their unpaid balances continue to carry forward.
- Payments are entered against the current or a future month, not a completed month.

## MongoDB
The default database name for this testing package is `yarlagadda_chits_test`, selected through `MONGO_DB_NAME`. This isolates test data from an existing `yarlagadda_chits` database. For local MongoDB use `mongodb://127.0.0.1:27017/`. For Atlas, copy the exact URI from Atlas → Connect → Drivers and URL-encode special characters in the password.

## Important
This is a management and bookkeeping application, not a regulated chit-fund compliance or accounting system. Verify applicable legal, tax and regulatory requirements before using it for real financial operations. Back up MongoDB regularly. Use a strong unique JWT secret and HTTPS before exposing the application publicly.

## Current dues and customer collection amount

The member list shows three separate figures for each participant:
- **Current due / unpaid:** remaining balance for the active instalment, including any earlier carried balance. Before the first due date, Month 1 is treated as the active instalment so advance or partial payments immediately show the unpaid remainder.
- **Next instalment:** the next month's premium less any payment already recorded against that month.
- **Ask customer (due + next):** current unpaid balance plus the next instalment remaining. This is a suggested amount to request, not a payment entry; recording a payment still requires using **Record payment**.

The scheme details page also shows the combined suggested collection amount across enrolled members. The calculation does not change payment records or mark anything as paid.
