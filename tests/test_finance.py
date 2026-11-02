"""School finance — expenses, income, salaries, payroll and the overview."""
from datetime import date

from tests.conftest import headers

TODAY = date.today().isoformat()
MONTH = date.today().strftime("%Y-%m")


async def _admin(client):
    return await headers(client, "admin@gss-ikeja.ng", "admin123")


async def test_expense_categories_and_expenses(ctx):
    client, ids = ctx
    h = await _admin(client)
    cat = (await client.post("/api/finance/expense-categories", headers=h,
                             json={"name": "Utilities"})).json()
    r = await client.post("/api/finance/expenses", headers=h, json={
        "spent_on": TODAY, "category_id": cat["id"], "description": "NEPA bill",
        "amount": 15000, "payee": "PHCN", "method": "transfer"})
    assert r.status_code == 201
    lst = (await client.get("/api/finance/expenses", headers=h)).json()
    assert lst["total"] == 15000
    assert lst["expenses"][0]["category"] == "Utilities"
    # zero/negative amounts are rejected
    bad = await client.post("/api/finance/expenses", headers=h, json={
        "spent_on": TODAY, "description": "x", "amount": 0})
    assert bad.status_code == 422


async def test_income(ctx):
    client, ids = ctx
    h = await _admin(client)
    await client.post("/api/finance/income", headers=h, json={
        "received_on": TODAY, "source": "PTA levy", "amount": 25000})
    lst = (await client.get("/api/finance/income", headers=h)).json()
    assert lst["total"] == 25000 and lst["income"][0]["source"] == "PTA levy"


async def test_salaries_and_payroll(ctx):
    client, ids = ctx
    h = await _admin(client)
    staff = (await client.get("/api/finance/salaries", headers=h)).json()
    # the seed has a school admin and a teacher
    assert {s["role"] for s in staff} >= {"school_admin", "teacher"}
    admin = next(s for s in staff if s["role"] == "school_admin")
    teacher = next(s for s in staff if s["role"] == "teacher")

    await client.put("/api/finance/salaries", headers=h, json={
        "staff_user_id": admin["staff_user_id"], "gross": 100000, "deduction": 10000})
    await client.put("/api/finance/salaries", headers=h, json={
        "staff_user_id": teacher["staff_user_id"], "gross": 60000})

    # run payroll for the month -> payslips generated from active salaries
    run = (await client.post("/api/finance/payroll", headers=h, json={"month": MONTH})).json()
    assert run["total_net"] == 150000      # 90000 + 60000
    detail = (await client.get(f"/api/finance/payroll/{run['id']}", headers=h)).json()
    assert detail["staff_count"] == 2 and detail["paid_count"] == 0

    # a second run for the same month is refused
    dup = await client.post("/api/finance/payroll", headers=h, json={"month": MONTH})
    assert dup.status_code == 409

    # pay everyone -> run becomes paid
    pa = (await client.post(f"/api/finance/payroll/{run['id']}/pay-all", headers=h)).json()
    assert pa["paid"] == 2 and pa["status"] == "paid"
    # a paid run cannot be deleted
    assert (await client.delete(f"/api/finance/payroll/{run['id']}", headers=h)).status_code == 409


async def test_overview_nets_everything(ctx):
    client, ids = ctx
    h = await _admin(client)
    # income, expense, and a paid payroll — all dated today (current month)
    await client.post("/api/finance/income", headers=h, json={
        "received_on": TODAY, "source": "Donation", "amount": 2000})
    await client.post("/api/finance/expenses", headers=h, json={
        "spent_on": TODAY, "description": "Chalk", "amount": 5000})
    staff = (await client.get("/api/finance/salaries", headers=h)).json()
    t = next(s for s in staff if s["role"] == "teacher")
    await client.put("/api/finance/salaries", headers=h, json={
        "staff_user_id": t["staff_user_id"], "gross": 60000})
    run = (await client.post("/api/finance/payroll", headers=h, json={"month": MONTH})).json()
    await client.post(f"/api/finance/payroll/{run['id']}/pay-all", headers=h)

    ov = (await client.get("/api/finance/overview", headers=h)).json()
    assert ov["fee_income"] == 0
    assert ov["other_income"] == 2000
    assert ov["expenses"] == 5000
    assert ov["payroll"] == 60000
    assert ov["net"] == 2000 - 5000 - 60000     # -63000


async def test_finance_rbac(ctx):
    client, ids = ctx
    # a teacher has no finance access
    th = await headers(client, "teacher@gss-ikeja.ng", "teach123")
    assert (await client.get("/api/finance/expenses", headers=th)).status_code == 403
    assert (await client.get("/api/finance/overview", headers=th)).status_code == 403
