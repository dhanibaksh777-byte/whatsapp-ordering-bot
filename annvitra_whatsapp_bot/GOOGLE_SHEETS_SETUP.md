# Google Sheets setup

1. Create a Google Cloud project.
2. Enable Google Sheets API and Google Drive API.
3. Create a service account and download its JSON key.
4. Place the JSON file beside the project as `service-account.json` (never commit it).
5. Share the menu spreadsheet with the service account email as Viewer.
6. Add a worksheet named `Menu` with headers in row 1:

   `name | price | qty | available`

7. Put one dish per row. `available` can be `TRUE` or `FALSE`.
8. Configure `.env`:

   ```env
   MENU_SOURCE=google_sheets
   GOOGLE_SHEET_ID=your_sheet_id
   GOOGLE_WORKSHEET=Menu
   GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
   ```

The sheet is currently read-only from the bot. Available stock is calculated as the sheet quantity minus active order reservations saved in the app database. Keep this in mind when manually editing quantities. For robust production inventory, make a transactional database the inventory source of truth and use Sheets as an owner-facing view or sync target.
