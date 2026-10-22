# Annvitra WhatsApp Ordering Bot — MVP

A FastAPI + Twilio WhatsApp ordering bot with:
- Customer menu, cart, delivery details, order review and confirmation
- SQLite order/session persistence
- Owner notifications for new orders
- Owner-only WhatsApp commands to mark UPI payments as paid and update order status
- Optional Google Sheets menu source
- Demo menu for local testing only

## Important architecture notes

- `MENU_SOURCE=demo` uses clearly fictional demo items. Do not use these prices or dishes for the real client.
- `MENU_SOURCE=google_sheets` reads the live menu from a Google Sheet. Configure the sheet columns as `name`, `price`, `qty`, `available`.
- Orders, customer sessions, and payment/order status are stored in SQLite by default. Set `DATABASE_URL` to PostgreSQL for deployment.
- The Google Sheet is read as the menu source; this MVP does not write stock changes back to the sheet. The database tracks reservations against the quantities read from the sheet. For a production multi-instance setup, make inventory authoritative in a transactional database or implement carefully synchronized sheet updates.
- Manual UPI payments are not automatically verified. The owner must inspect their payment account and send `PAID ANN-...` from the configured owner WhatsApp number.
- Cash is marked paid only after the owner sends `CASHRECEIVED ANN-...`.
- Twilio must be configured for WhatsApp. For sandbox testing, join the sandbox from both the customer test number and the owner number as required by Twilio.
- Depending on Twilio's current WhatsApp rules, outbound messages outside the customer-service window may require an approved template.

## 1. Create a virtual environment

Windows PowerShell, from this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your own credentials. Never commit `.env`.

## 2. Run locally

```powershell
uvicorn app.main:app --reload
```

Health endpoint: `http://127.0.0.1:8000/health`

The local server cannot receive real WhatsApp messages until you expose it using an HTTPS tunnel (for example, a tunnel service you trust) and set the Twilio webhook URL to:

`https://YOUR_PUBLIC_HTTPS_URL/webhook/whatsapp`

Set the Twilio webhook method to `POST`.

## 3. Demo mode

Set:

```env
MENU_SOURCE=demo
```

The demo menu is fictional. Start the app and use Twilio's WhatsApp sandbox to test, or POST form fields `From` and `Body` to `/webhook/whatsapp` locally.

## 4. Google Sheets mode

Set:

```env
MENU_SOURCE=google_sheets
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_WORKSHEET=Menu
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
```

Share the Google Sheet with the service account email from your Google service-account JSON file.

Required first-row headers:

| name | price | qty | available |
|---|---:|---:|---|
| Dish name | 250 | 10 | TRUE |

`available` may be TRUE/FALSE. `qty` must be a non-negative integer and `price` a non-negative number.

Do not upload the service-account JSON or `.env` to GitHub.

## 5. Owner commands

Send these commands from the exact WhatsApp number configured in `OWNER_WHATSAPP_NUMBER`:

- `ORDERS` — show recent active orders
- `ORDER ANN-...` — show an order's details
- `PAID ANN-...` — mark a UPI payment as paid (only after checking actual payment)
- `CASHRECEIVED ANN-...` — mark a cash payment as received
- `PREPARING ANN-...` — update order status
- `OUTFORDELIVERY ANN-...` — update order status
- `DELIVERED ANN-...` — mark order delivered
- `CANCEL ANN-...` — cancel an order and release its reservation (only before delivered)

The owner phone is authorized by sender ID, not by the message body. Keep that number secret and protect your Twilio account credentials.

## 6. Customer flow

1. Customer messages the bot (e.g. `hi`).
2. Bot shows available menu.
3. Customer sends `1 2` to add two of item 1.
4. Customer uses `cart`, `menu`, `remove 1`, `done`, or `cancel`.
5. Bot asks for name, delivery contact, and complete address.
6. Bot displays order summary and asks for `confirm` or `cancel`.
7. Bot creates an order ID, reserves the stock in the app database, and notifies the owner.
8. Customer chooses `upi` or `cash`.
9. Bot provides configured UPI instructions or explains cash-on-delivery.
10. Owner verifies UPI manually and sends `PAID ORDER_ID`, or confirms cash receipt with `CASHRECEIVED ORDER_ID`.

## 7. Before production

- Use PostgreSQL, not SQLite, for deployment with multiple workers/instances.
- Add Twilio webhook signature validation (`TWILIO_VALIDATE_SIGNATURE=true`) and configure the public URL correctly.
- Set `PUBLIC_BASE_URL` to the externally reachable HTTPS base URL.
- Configure a real UPI payment provider or maintain manual verification.
- Decide how long unpaid orders hold stock and implement expiry/release.
- Ensure menu stock in Google Sheets is reconciled with actual kitchen inventory.
- Add rate limiting, monitoring, backups, privacy policy, and data-retention rules.
- Test cancellation, duplicate messages, concurrent orders, webhook retries, and failed outbound notifications.
