# Backend API Documentation

## Overview

This backend is a Django REST Framework API for:

- User registration and email/password login
- Mobile JWT authentication
- Admin-created payment requests with optional fixed amounts
- QR code and transaction ID visibility
- User screenshot, amount, and text submissions
- Admin final-amount confirmation, acceptance, or decline
- Automatic one-time balance crediting using the confirmed final amount
- Balance history and dashboard summaries
- One-to-one chat between a user and an admin

## Base URL

Local development:

```text
http://127.0.0.1:8000
```

All endpoints start with:

```text
/api/v1/
```

All endpoint paths end with `/`.

## Start the backend

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py runserver
```

Create the first admin account:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

The admin account must be created with the backend command above. Public registration always creates a normal user.

## Authentication

Public endpoints:

- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/token/`
- `POST /api/v1/auth/token/refresh/`

All other endpoints require an access token:

```http
Authorization: Bearer <access_token>
```

Admin endpoints require an access token belonging to a user with `is_staff=true`.

Access tokens expire after 15 minutes. Refresh tokens expire after 7 days. Refresh tokens rotate, and the previous refresh token is blacklisted after it is used.

## Request conventions

- Send JSON requests with `Content-Type: application/json`.
- Send QR and screenshot uploads as `multipart/form-data`.
- Image uploads must be PNG, JPG, or WebP.
- Image uploads must not exceed 5 MB.
- Image dimensions must not exceed 25 million pixels.
- Fixed request amounts, user-proposed amounts, and admin final amounts are decimal values with a minimum of `0.01` and no more than two decimal places. A payment request amount may be `null`; `final_amount` is required when accepting a submission.
- Text, instructions, decline reasons, and chat messages are limited to 2,000 characters.
- Transaction IDs are limited to 100 characters and must be unique.
- IDs are integer values.
- Timestamps use ISO 8601 UTC format.

## Pagination

List endpoints use page-number pagination. Send `?page=1` to request a page and `?page_size` is not configurable in the current MVP.

Example:

```json
{
  "count": 21,
  "next": "http://127.0.0.1:8000/api/v1/submissions/?page=2",
  "previous": null,
  "results": []
}
```

Each page contains up to 20 records.

## Endpoint summary

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/register/` | Public | Register a user and return JWTs |
| `POST` | `/api/v1/auth/token/` | Public | Log in with email and password |
| `POST` | `/api/v1/auth/token/refresh/` | Public | Rotate JWTs |
| `POST` | `/api/v1/auth/logout/` | User | Blacklist a refresh token |
| `GET` | `/api/v1/auth/me/` | User | Get the current user |
| `GET` | `/api/v1/dashboard/` | User | Get balance and recent activity |
| `GET` | `/api/v1/payment-requests/` | User | List published payment requests |
| `GET` | `/api/v1/payment-requests/{id}/` | User | Get a published payment request |
| `POST` | `/api/v1/payment-requests/{id}/submissions/` | User | Submit screenshot, proposed amount when required, and text |
| `GET` | `/api/v1/submissions/` | User | List the current user's submissions |
| `GET` | `/api/v1/submissions/{id}/` | Owner | Get one owned submission |
| `GET` | `/api/v1/balance-history/` | User | List the current user's balance history |
| `GET` | `/api/v1/withdrawals/balance/` | User | Get balance, reserved amount, and available balance |
| `GET` | `/api/v1/withdrawals/` | User | List the current user's withdrawal requests |
| `POST` | `/api/v1/withdrawals/` | User | Create an INR withdrawal request with 1 to 5 payees |
| `GET` | `/api/v1/withdrawals/{id}/` | Owner | Get one owned withdrawal request |
| `GET` | `/api/v1/chat/` | User | Get chat message and unread counts |
| `GET` | `/api/v1/chat/messages/` | User | List the current user's chat thread and mark it read |
| `POST` | `/api/v1/chat/messages/` | User | Send a chat message to the admins |
| `GET` | `/api/v1/files/payment-requests/{id}/qr/` | User/Admin | Download an authorized QR image |
| `GET` | `/api/v1/files/submissions/{id}/screenshot/` | Owner/Admin | Download an authorized screenshot |
| `GET` | `/api/v1/admin/payment-requests/` | Admin | List all payment requests |
| `POST` | `/api/v1/admin/payment-requests/` | Admin | Create a payment request |
| `GET` | `/api/v1/admin/payment-requests/{id}/` | Admin | Get any payment request |
| `PUT` | `/api/v1/admin/payment-requests/{id}/` | Admin | Fully replace writable request fields |
| `PATCH` | `/api/v1/admin/payment-requests/{id}/` | Admin | Partially update a request |
| `DELETE` | `/api/v1/admin/payment-requests/{id}/` | Admin | Delete a request without submissions |
| `DELETE` | `/api/v1/admin/payment-requests/{id}/force-delete/` | Admin | Force-delete a request and its dependent records |
| `GET` | `/api/v1/admin/submissions/` | Admin | List and filter all submissions |
| `GET` | `/api/v1/admin/submissions/{id}/` | Admin | Get any submission |
| `POST` | `/api/v1/admin/submissions/{id}/accept/` | Admin | Confirm `final_amount`, accept, and credit the user |
| `POST` | `/api/v1/admin/submissions/{id}/decline/` | Admin | Decline with a reason |
| `GET` | `/api/v1/admin/users/` | Admin | List and search users |
| `GET` | `/api/v1/admin/users/{id}/` | Admin | Get a user and balance |
| `GET` | `/api/v1/admin/balance-history/` | Admin | List all balance entries |
| `GET` | `/api/v1/admin/withdrawals/` | Admin | List and filter all withdrawal requests |
| `GET` | `/api/v1/admin/withdrawals/summary/` | Admin | Aggregate counts and change watermark for polling |
| `GET` | `/api/v1/admin/withdrawals/{id}/` | Admin | Get any withdrawal request |
| `POST` | `/api/v1/admin/withdrawals/{id}/confirm/` | Admin | Confirm the payout, debit the balance, and record a `DEBIT` entry |
| `POST` | `/api/v1/admin/withdrawals/{id}/reject/` | Admin | Reject with a reason and release the reserved amount |
| `GET` | `/api/v1/admin/chat/conversations/` | Admin | List the chat inbox of all non-staff users |
| `GET` | `/api/v1/admin/chat/users/{id}/messages/` | Admin | Get one user's chat thread and mark it read |
| `POST` | `/api/v1/admin/chat/users/{id}/messages/` | Admin | Send a chat message to one user |

# Authentication API

## 1. Register a user

```http
POST /api/v1/auth/register/
```

No authentication is required.

### Request

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "first_name": "John",
  "last_name": "Doe"
}
```

Fields:

| Field | Type | Required | Rules |
|---|---|---|---|
| `email` | string | Yes | Unique and stored in lowercase |
| `password` | string | Yes | Must pass Django password validation |
| `first_name` | string | No | Maximum 100 characters |
| `last_name` | string | No | Maximum 100 characters |

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "StrongPass123!",
    "first_name": "John",
    "last_name": "Doe"
  }'
```

### Success response: `201 Created`

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "balance": "0.00"
  }
}
```

### Error response: `400 Bad Request`

```json
{
  "email": [
    "An account with this email already exists."
  ]
}
```

Registration is limited to 10 requests per hour per client address.

---

## 2. Log in

```http
POST /api/v1/auth/token/
```

No authentication is required.

### Request

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/token/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "StrongPass123!"
  }'
```

### Success response: `200 OK`

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "balance": "0.00"
  }
}
```

### Error response: `401 Unauthorized`

```json
{
  "detail": "No active account found with the given credentials"
}
```

Login is limited to 10 requests per minute per client address.

---

## 3. Refresh and rotate tokens

```http
POST /api/v1/auth/token/refresh/
```

No access token is required.

### Request

```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/token/refresh/" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }'
```

### Success response: `200 OK`

A new access token and rotated refresh token are returned.

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

Store both returned values. The old refresh token cannot be used again.

### Error response: `401 Unauthorized`

```json
{
  "detail": "Token is blacklisted"
}
```

The detail can also report an invalid or expired token.

---

## 4. Log out

```http
POST /api/v1/auth/logout/
```

Requires an access token and a refresh token.

### Request headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request

```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/logout/" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }'
```

### Success response: `205 Reset Content`

The response has no body.

### Error response: `400 Bad Request`

```json
{
  "refresh": [
    "This field is required."
  ]
}
```

Or:

```json
{
  "detail": "Invalid or expired refresh token."
}
```

---

## 5. Get the current user

```http
GET /api/v1/auth/me/
```

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/auth/me/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "balance": "125.50"
}
```

# User API

## 6. Get the user dashboard

```http
GET /api/v1/dashboard/
```

This endpoint is not paginated. It returns the current balance, counts, and the five most recent records of each type.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/dashboard/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "balance": 125.5,
  "available_balance": 25.5,
  "active_request_count": 2,
  "pending_submission_count": 1,
  "accepted_submission_count": 1,
  "pending_withdrawal_count": 1,
  "recent_payment_requests": [
    {
      "id": 2,
      "amount": "250.00",
      "transaction_id": "TXN-200",
      "instructions": "Pay the exact amount.",
      "status": "PUBLISHED",
      "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/2/qr/",
      "created_at": "2026-09-25T10:00:00Z"
    }
  ],
  "recent_submissions": [
    {
      "id": 11,
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "125.50"
      },
      "payment_request": {
        "id": 1,
        "amount": "125.50",
        "transaction_id": "TXN-100",
        "instructions": "Pay the exact amount.",
        "status": "PUBLISHED",
        "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
        "created_at": "2026-09-25T09:00:00Z"
      },
      "screenshot_url": "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/",
      "proposed_amount": "125.50",
      "text": "Payment completed.",
      "attempt": 1,
      "status": "ACCEPTED",
      "decline_reason": "",
      "final_amount": "125.50",
      "reviewed_at": "2026-09-25T10:30:00Z",
      "created_at": "2026-09-25T10:15:00Z",
      "updated_at": "2026-09-25T10:30:00Z"
    }
  ],
  "recent_balance_entries": [
    {
      "id": 3,
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "125.50"
      },
      "amount": "125.50",
      "balance_after": "125.50",
      "entry_type": "CREDIT",
      "payment_request_id": 1,
      "submission_id": 11,
      "withdrawal_id": null,
      "created_at": "2026-09-25T10:30:00Z"
    }
  ]
}
```

---

## 7. List published payment requests

```http
GET /api/v1/payment-requests/
```

Only requests with `status=PUBLISHED` are returned. Closed requests are excluded. The `amount` field is `null` when the user must enter the amount paid with a submission; clients should treat `null` as no fixed amount.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/payment-requests/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "amount": "125.50",
      "transaction_id": "TXN-100",
      "instructions": "Pay the exact amount.",
      "status": "PUBLISHED",
      "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
      "created_at": "2026-09-25T09:00:00Z"
    }
  ]
}
```

---

## 8. Get a published payment request

```http
GET /api/v1/payment-requests/{id}/
```

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/payment-requests/1/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "id": 1,
  "amount": "125.50",
  "transaction_id": "TXN-100",
  "instructions": "Pay the exact amount.",
  "status": "PUBLISHED",
  "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
  "created_at": "2026-09-25T09:00:00Z"
}
```

A closed request is returned as not found to normal users. If `amount` is `null`, the user must provide `proposed_amount` when submitting the payment proof.

### Error response: `404 Not Found`

```json
{
  "detail": "Not found."
}
```

---

## 9. Submit a screenshot and text

```http
POST /api/v1/payment-requests/{id}/submissions/
```

The payment request must be published. A user can have only one pending submission and one accepted submission for each request. If the request has a fixed amount, the backend snapshots that amount as `proposed_amount`; if it has no fixed amount, the user must provide `proposed_amount`.

### Request headers

```http
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

### Form fields

| Field | Type | Required | Rules |
|---|---|---|---|
| `screenshot` | file | Yes | PNG, JPG, or WebP; maximum 5 MB |
| `proposed_amount` | decimal string | If request amount is blank | User-entered amount; minimum `0.01`; maximum two decimal places |
| `text` | string | Yes | Non-empty; maximum 2,000 characters |

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/payment-requests/1/submissions/" \
  -H "Authorization: Bearer <access_token>" \
  -F "screenshot=@payment-screenshot.png" \
  -F "proposed_amount=75.25" \
  -F "text=Payment completed successfully."
```

### Success response: `201 Created`

```json
{
  "id": 11,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "balance": "0.00"
  },
  "payment_request": {
    "id": 1,
    "amount": null,
    "transaction_id": "TXN-100",
    "instructions": "Pay the amount you choose.",
    "status": "PUBLISHED",
    "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
    "created_at": "2026-09-25T09:00:00Z"
  },
  "screenshot_url": "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/",
  "proposed_amount": "75.25",
  "text": "Payment completed successfully.",
  "attempt": 1,
  "status": "PENDING",
  "final_amount": null,
  "decline_reason": "",
  "reviewed_at": null,
  "created_at": "2026-09-25T10:15:00Z",
  "updated_at": "2026-09-25T10:15:00Z"
}
```

### Common error responses

Missing amount for a request without a fixed amount:

```json
{
  "proposed_amount": [
    "Enter the amount you paid for this request."
  ]
}
```

A proposed amount that conflicts with a fixed request amount returns:

```json
{
  "proposed_amount": [
    "This request has a fixed amount."
  ]
}
```

Duplicate pending submission:

```json
{
  "detail": "You already have a pending submission for this request."
}
```

Already accepted:

```json
{
  "detail": "This request has already been accepted for your account."
}
```

Closed request:

```json
{
  "detail": "Not found."
}
```

Invalid image:

```json
{
  "screenshot": [
    "Upload a valid image file."
  ]
}
```

---

## 10. List the current user's submissions

```http
GET /api/v1/submissions/
```

Only submissions owned by the authenticated user are returned.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/submissions/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 11,
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "125.50"
      },
      "payment_request": {
        "id": 1,
        "amount": null,
        "transaction_id": "TXN-100",
        "instructions": "Pay the amount you choose.",
        "status": "PUBLISHED",
        "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
        "created_at": "2026-09-25T09:00:00Z"
      },
      "screenshot_url": "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/",
      "proposed_amount": "75.25",
      "text": "Payment completed successfully.",
      "attempt": 1,
      "status": "ACCEPTED",
      "final_amount": "80.00",
      "decline_reason": "",
      "reviewed_at": "2026-09-25T10:30:00Z",
      "created_at": "2026-09-25T10:15:00Z",
      "updated_at": "2026-09-25T10:30:00Z"
    }
  ]
}
```

---

## 11. Get one owned submission

```http
GET /api/v1/submissions/{id}/
```

Only the owner or an admin can access this record. Other users receive `404` so the API does not reveal that another user's submission exists.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/submissions/11/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

The response has the same submission object shown in the submission list.

### Error response: `404 Not Found`

```json
{
  "detail": "Not found."
}
```

---

## 12. Get the current user's balance history

```http
GET /api/v1/balance-history/
```

Balance entries are immutable ledger rows. `CREDIT` entries are created when an admin accepts a submission, and `DEBIT` entries are created when an admin confirms a withdrawal payout. Every entry's `amount` equals the source amount, and `balance_after` is the user balance right after the entry.

`payment_request_id`, `submission_id`, and `withdrawal_id` identify the source: credit entries point at a submission and debit entries point at a withdrawal. `entry_type` is `CREDIT` or `DEBIT`.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/balance-history/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 3,
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "125.50"
      },
      "amount": "125.50",
      "balance_after": "125.50",
      "entry_type": "CREDIT",
      "payment_request_id": 1,
      "submission_id": 11,
      "withdrawal_id": null,
      "created_at": "2026-09-25T10:30:00Z"
    }
  ]
}
```

# Protected File API

Image files are not public static files. Every file request must include an access token.

Mobile clients should download the URL as bytes and display the returned image bytes.

## 13. Download a QR code

```http
GET /api/v1/files/payment-requests/{id}/qr/
```

Access rules:

- Admins can download every QR image.
- Users can download a published request QR image.
- A user can download a closed request QR image only if that user has a submission for the request.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/" \
  -H "Authorization: Bearer <access_token>" \
  --output qr.png
```

### Success response: `200 OK`

```http
Content-Type: image/png
```

The response body is the binary QR image, not JSON.

### Error response: `404 Not Found`

```json
{
  "detail": "Not found."
}
```

---

## 14. Download a submission screenshot

```http
GET /api/v1/files/submissions/{id}/screenshot/
```

Only the submission owner or an admin can download the screenshot.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/" \
  -H "Authorization: Bearer <access_token>" \
  --output screenshot.png
```

### Success response: `200 OK`

```http
Content-Type: image/png
```

The response body is the binary screenshot, not JSON.

# Admin API

Every endpoint in this section requires an admin access token.

```http
Authorization: Bearer <admin_access_token>
```

## 15. List all payment requests

```http
GET /api/v1/admin/payment-requests/
```

This endpoint includes both `PUBLISHED` and `CLOSED` requests.

### Request

```bash
curl "http://127.0.0.1:8000/api/v1/admin/payment-requests/" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "amount": "125.50",
      "transaction_id": "TXN-100",
      "qr_image": "payment-requests/uuid/qr.png",
      "instructions": "Pay the exact amount.",
      "status": "PUBLISHED",
      "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
      "created_by": {
        "id": 2,
        "email": "admin@example.com",
        "first_name": "Admin",
        "last_name": "User",
        "balance": "0.00"
      },
      "submission_count": 0,
      "created_at": "2026-09-25T09:00:00Z",
      "updated_at": "2026-09-25T09:00:00Z"
    }
  ]
}
```

Use `qr_image_url` to download the image. `qr_image` is the internal storage path. `submission_count` is the number of submissions currently attached to the request and is used to decide whether it can be deleted normally.

---

## 16. Create a payment request

```http
POST /api/v1/admin/payment-requests/
```

### Request headers

```http
Authorization: Bearer <admin_access_token>
Content-Type: multipart/form-data
```

### Form fields

| Field | Type | Required | Rules |
|---|---|---|---|
| `amount` | decimal string | No | Fixed amount with a minimum of `0.01`; omit or send blank/null for a user-defined amount; maximum two decimal places |
| `transaction_id` | string | Yes | Unique; maximum 100 characters |
| `qr_image` | file | Yes | PNG, JPG, or WebP; maximum 5 MB |
| `instructions` | string | No | Maximum 2,000 characters |
| `status` | string | No | `PUBLISHED` by default; optionally `CLOSED` |

Leave `amount` blank to create a request where each user enters the amount they paid with their submission.

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/payment-requests/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -F "amount=125.50" \
  -F "transaction_id=TXN-100" \
  -F "instructions=Pay the exact amount." \
  -F "qr_image=@payment-qr.png"
```

### Success response: `201 Created`

```json
{
  "id": 1,
  "amount": "125.50",
  "transaction_id": "TXN-100",
  "qr_image": "payment-requests/uuid/qr.png",
  "instructions": "Pay the exact amount.",
  "status": "PUBLISHED",
  "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
  "created_by": {
    "id": 2,
    "email": "admin@example.com",
    "first_name": "Admin",
    "last_name": "User",
    "balance": "0.00"
  },
  "created_at": "2026-09-25T09:00:00Z",
  "updated_at": "2026-09-25T09:00:00Z"
}
```

### Common error response: `400 Bad Request`

```json
{
  "transaction_id": [
    "This field must be unique."
  ]
}
```

---

## 17. Get any payment request as admin

```http
GET /api/v1/admin/payment-requests/{id}/
```

This endpoint can return both published and closed requests.

### Request

```bash
curl "http://127.0.0.1:8000/api/v1/admin/payment-requests/1/" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

The response uses the same payment request object returned by the create endpoint.

---

## 18. Update a payment request

```http
PATCH /api/v1/admin/payment-requests/{id}/
```

`PATCH` updates only the supplied fields. It is the recommended update method. Send `amount: null` (or a blank multipart value) to clear a fixed amount and make the request user-defined.

### Request: close a request

```json
{
  "status": "CLOSED"
}
```

Example request:

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/admin/payment-requests/1/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "CLOSED"
  }'
```

### Request: change amount and instructions

```json
{
  "amount": "150.00",
  "instructions": "Updated payment instructions."
}
```

### Request: replace the QR image

Send `multipart/form-data`:

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/admin/payment-requests/1/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -F "qr_image=@replacement-qr.png"
```

### Success response: `200 OK`

```json
{
  "id": 1,
  "amount": "150.00",
  "transaction_id": "TXN-100",
  "qr_image": "payment-requests/uuid/qr.png",
  "instructions": "Updated payment instructions.",
  "status": "CLOSED",
  "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
  "created_by": {
    "id": 2,
    "email": "admin@example.com",
    "first_name": "Admin",
    "last_name": "User",
    "balance": "0.00"
  },
  "submission_count": 0,
  "created_at": "2026-09-25T09:00:00Z",
  "updated_at": "2026-09-25T11:00:00Z"
}
```

Closing a request prevents new submissions. Existing pending submissions remain available for admin review. Changing a request's `amount` does not rewrite `proposed_amount` on submissions that were already created.

---

## 19. Fully update a payment request

```http
PUT /api/v1/admin/payment-requests/{id}/
```

A full update should send `amount`, `transaction_id`, and `qr_image`. `amount` may be blank or `null` to make the request user-defined. `instructions` and `status` are optional.

### JSON request without changing the image is not supported for full `PUT`

Use `PATCH` when only JSON fields are changing. To use `PUT`, resend all writable fields, including the QR file, using `multipart/form-data`.

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/admin/payment-requests/1/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -F "amount=150.00" \
  -F "transaction_id=TXN-100" \
  -F "instructions=Updated payment instructions." \
  -F "status=PUBLISHED" \
  -F "qr_image=@payment-qr.png"
```

### Success response: `200 OK`

The response is the complete updated payment request object.

---

## 20. List and filter all submissions

```http
GET /api/v1/admin/submissions/
```

### Query parameters

| Parameter | Type | Description |
|---|---|---|
| `status` | string | `PENDING`, `ACCEPTED`, or `DECLINED` |
| `user_id` | integer | Filter by user ID |
| `payment_request_id` | integer | Filter by payment request ID |
| `page` | integer | Pagination page |

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/admin/submissions/?status=PENDING&user_id=1" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

Each submission includes `proposed_amount` (the amount submitted, or the request's fixed amount) and `final_amount` (`null` until acceptance, then the exact amount credited).

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 11,
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "0.00"
      },
      "payment_request": {
        "id": 1,
        "amount": null,
        "transaction_id": "TXN-100",
        "instructions": "Pay the amount you choose.",
        "status": "PUBLISHED",
        "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
        "created_at": "2026-09-25T09:00:00Z"
      },
      "screenshot_url": "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/",
      "proposed_amount": "75.25",
      "text": "Payment completed successfully.",
      "attempt": 1,
      "status": "PENDING",
      "decline_reason": "",
      "final_amount": null,
      "reviewed_at": null,
      "created_at": "2026-09-25T10:15:00Z",
      "updated_at": "2026-09-25T10:15:00Z"
    }
  ]
}
```

### Invalid filter response: `400 Bad Request`

```json
{
  "status": [
    "Invalid submission status."
  ]
}
```

---

## 21. Get any submission as admin

```http
GET /api/v1/admin/submissions/{id}/
```

### Request

```bash
curl "http://127.0.0.1:8000/api/v1/admin/submissions/11/" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

The response is the complete submission object shown in the admin submission list.

---

## 22. Accept a submission

```http
POST /api/v1/admin/submissions/{id}/accept/
```

Accepting a pending submission requires the admin to confirm the amount that will be credited:

- Changes its status to `ACCEPTED`
- Stores the confirmed value as `final_amount`
- Credits that exact value to the user, even when it differs from `proposed_amount`
- Creates a balance-history entry using the same final amount
- Prevents another accepted submission for the same user and request
- Is safe to retry with the same final amount because it cannot credit the balance twice

### Request

Send `final_amount` in a JSON body. It must be at least `0.01` and have no more than two decimal places.

```json
{
  "final_amount": "80.00"
}
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/submissions/11/accept/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "final_amount": "80.00"
  }'
```

### Success response: `200 OK`

```json
{
  "id": 11,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "balance": "125.50"
  },
  "payment_request": {
    "id": 1,
    "amount": null,
    "transaction_id": "TXN-100",
    "instructions": "Pay the amount you choose.",
    "status": "PUBLISHED",
    "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
    "created_at": "2026-09-25T09:00:00Z"
  },
  "screenshot_url": "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/",
  "proposed_amount": "75.25",
  "text": "Payment completed successfully.",
  "attempt": 1,
  "status": "ACCEPTED",
  "final_amount": "80.00",
  "decline_reason": "",
  "reviewed_at": "2026-09-25T10:30:00Z",
  "created_at": "2026-09-25T10:15:00Z",
  "updated_at": "2026-09-25T10:30:00Z"
}
```

### Error response: `400 Bad Request`

```json
{
  "final_amount": [
    "This field is required."
  ]
}
```

A missing, non-numeric, or less-than-`0.01` final amount returns the same `400` status with a `final_amount` validation error. Accepting a declined submission returns `400 Bad Request` with `Only pending submissions can be accepted.`

### Conflict response: `409 Conflict`

If the submission was already accepted with a different amount, the balance is not changed:

```json
{
  "detail": "This submission was already accepted with a different amount."
}
```

A repeated request for an already accepted submission with the same final amount returns `200 OK` and does not add another balance entry.

---

## 23. Decline a submission

```http
POST /api/v1/admin/submissions/{id}/decline/
```

The user can submit a new screenshot and text after a decline. The new submission receives the next attempt number.

### Request

```json
{
  "reason": "The transaction screenshot is unclear."
}
```

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/submissions/11/decline/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "The transaction screenshot is unclear."
  }'
```

### Success response: `200 OK`

```json
{
  "id": 11,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "balance": "0.00"
  },
  "payment_request": {
    "id": 1,
    "amount": null,
    "transaction_id": "TXN-100",
    "instructions": "Pay the amount you choose.",
    "status": "PUBLISHED",
    "qr_image_url": "http://127.0.0.1:8000/api/v1/files/payment-requests/1/qr/",
    "created_at": "2026-09-25T09:00:00Z"
  },
  "screenshot_url": "http://127.0.0.1:8000/api/v1/files/submissions/11/screenshot/",
  "proposed_amount": "75.25",
  "text": "Payment completed successfully.",
  "attempt": 1,
  "status": "DECLINED",
  "decline_reason": "The transaction screenshot is unclear.",
  "final_amount": null,
  "reviewed_at": "2026-09-25T10:30:00Z",
  "created_at": "2026-09-25T10:15:00Z",
  "updated_at": "2026-09-25T10:30:00Z"
}
```

### Missing reason response: `400 Bad Request`

```json
{
  "reason": [
    "This field is required."
  ]
}
```

An already accepted or declined submission returns:

```json
{
  "detail": "Only pending submissions can be declined."
}
```

---

## 24. List and search users

```http
GET /api/v1/admin/users/
```

### Query parameters

| Parameter | Type | Description |
|---|---|---|
| `search` | string | Search email, first name, or last name |
| `page` | integer | Pagination page |

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/admin/users/?search=user@example.com" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "balance": "125.50",
      "submission_count": 1,
      "withdrawal_count": 2,
      "pending_withdrawal_amount": "400.00",
      "is_active": true,
      "is_staff": false,
      "date_joined": "2026-09-25T08:00:00Z",
      "last_login": "2026-09-25T10:00:00Z"
    }
  ]
}
```

---

## 25. Get a user as admin

```http
GET /api/v1/admin/users/{id}/
```

### Request

```bash
curl "http://127.0.0.1:8000/api/v1/admin/users/1/" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "balance": "125.50",
  "submission_count": 1,
  "withdrawal_count": 2,
  "pending_withdrawal_amount": "400.00",
  "is_active": true,
  "is_staff": false,
  "date_joined": "2026-09-25T08:00:00Z",
  "last_login": "2026-09-25T10:00:00Z"
}
```

---

## 26. List all balance history as admin

```http
GET /api/v1/admin/balance-history/
```

### Query parameters

| Parameter | Type | Description |
|---|---|---|
| `user_id` | integer | Filter by user ID |
| `page` | integer | Pagination page |

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/admin/balance-history/?user_id=1" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 3,
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "125.50"
      },
      "amount": "125.50",
      "balance_after": "125.50",
      "entry_type": "CREDIT",
      "payment_request_id": 1,
      "submission_id": 11,
      "withdrawal_id": null,
      "created_at": "2026-09-25T10:30:00Z"
    }
  ]
}
```

---

## 27. Delete a payment request without submissions

```http
DELETE /api/v1/admin/payment-requests/{id}/
```

A request can be deleted normally only when it has no submissions. The QR image is removed with the request.

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/admin/payment-requests/1/" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `204 No Content`

The response has no body.

### Conflict response: `409 Conflict`

```json
{
  "detail": "This payment request has submissions and cannot be deleted. Close it instead."
}
```

Use the force-delete endpoint only when the request and its dependent records must be removed.

---

## 28. Force-delete a payment request

```http
DELETE /api/v1/admin/payment-requests/{id}/force-delete/
```

This is an irreversible admin operation. It removes the request, all of its submissions and screenshots, and all related balance entries, then recalculates each affected account balance from the remaining entries.

Send the request's exact `transaction_id` as confirmation:

```json
{
  "confirm_transaction_id": "TXN-100"
}
```

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/admin/payment-requests/1/force-delete/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "confirm_transaction_id": "TXN-100"
  }'
```

### Success response: `204 No Content`

The response has no body. Stored QR and submission files are deleted after the database transaction commits.

### Confirmation error: `400 Bad Request`

```json
{
  "detail": "The transaction ID confirmation does not match this payment request."
}
```

---

# Chat API

Chat is a direct conversation between one user and the admins. Every user has exactly one permanent thread, created automatically the first time it is needed.

Messaging rules:

- A user can only read and send messages in their own thread.
- There is no endpoint that accepts a recipient, so a user cannot message another user.
- Only an admin can choose which user to write to, and only non-staff users are listed or reachable.
- Messages are text only. Images stay in the submission flow.
- `unread_count` counts the messages the other side has not read yet. A user's own messages are never unread for that user, and an admin's own messages are never unread for the admin.
- Reading a thread marks the other side's messages in it as read. For a user, `unread_count` counts unread admin messages. For an admin, the inbox `unread_count` counts unread user messages.

## 29. Get the chat summary

```http
GET /api/v1/chat/
```

This endpoint is not paginated. It returns the message counts and the most recent message of the current user's thread.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/chat/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "message_count": 2,
  "unread_count": 1,
  "last_message": {
    "id": 32,
    "sender": {
      "id": 1,
      "email": "admin@example.com",
      "first_name": "Admin",
      "last_name": "User",
      "balance": "0.00"
    },
    "body": "Thanks, we are checking it now.",
    "created_at": "2026-09-25T11:00:00Z"
  },
  "last_message_at": "2026-09-25T11:00:00Z"
}
```

A thread with no messages returns zero counts with `last_message` and `last_message_at` set to `null`.

---

## 30. List the current user's chat thread

```http
GET /api/v1/chat/messages/
```

Messages are returned oldest first. This request also marks the admin's messages in the thread as read, so the `unread_count` from `GET /api/v1/chat/` becomes `0` after it.

### Request headers

```http
Authorization: Bearer <access_token>
```

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/chat/messages/" \
  -H "Authorization: Bearer <access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 31,
      "sender": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "0.00"
      },
      "body": "My submission screenshot is unclear.",
      "created_at": "2026-09-25T10:45:00Z"
    },
    {
      "id": 32,
      "sender": {
        "id": 2,
        "email": "admin@example.com",
        "first_name": "Admin",
        "last_name": "User",
        "balance": "0.00"
      },
      "body": "Thanks, we are checking it now.",
      "created_at": "2026-09-25T11:00:00Z"
    }
  ]
}
```

`sender` is `null` when the account that sent the message has been deleted.

---

## 31. Send a chat message

```http
POST /api/v1/chat/messages/
```

### Request headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request

```json
{
  "body": "My submission screenshot is unclear."
}
```

Fields:

| Field | Type | Required | Rules |
|---|---|---|---|
| `body` | string | Yes | Non-empty; maximum 2,000 characters |

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/chat/messages/" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "My submission screenshot is unclear."
  }'
```

### Success response: `201 Created`

```json
{
  "id": 33,
  "sender": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "balance": "125.50"
  },
  "body": "My submission screenshot is unclear.",
  "created_at": "2026-09-25T11:20:00Z"
}
```

### Error response: `400 Bad Request`

```json
{
  "body": [
    "This field may not be blank."
  ]
}
```

---

## 32. List the chat inbox

```http
GET /api/v1/admin/chat/conversations/
```

This endpoint lists every non-staff user, including users who have never sent a message, so an admin can start a conversation. Threads with recent activity are returned first, and the remaining users follow in email order.

### Query parameters

| Parameter | Type | Description |
|---|---|---|
| `search` | string | Search email, first name, or last name |
| `page` | integer | Pagination page |

Example request:

```bash
curl "http://127.0.0.1:8000/api/v1/admin/chat/conversations/?search=user@example.com" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "125.50"
      },
      "message_count": 2,
      "unread_count": 1,
      "last_message_id": 32,
      "last_message_body": "Thanks, we are checking it now.",
      "last_message_sender_id": 2,
      "last_message_at": "2026-09-25T11:00:00Z"
    },
    {
      "user": {
        "id": 3,
        "email": "new@example.com",
        "first_name": "New",
        "last_name": "User",
        "balance": "0.00"
      },
      "message_count": 0,
      "unread_count": 0,
      "last_message_id": null,
      "last_message_body": null,
      "last_message_sender_id": null,
      "last_message_at": null
    }
  ]
}
```

`unread_count` counts the user's messages that the admin has not read yet. The `last_message_*` fields are `null` for a user with no messages.

---

## 33. Read or send messages for one user

```http
GET /api/v1/admin/chat/users/{id}/messages/
POST /api/v1/admin/chat/users/{id}/messages/
```

`{id}` is the user ID from the inbox. Messages are returned oldest first. `GET` also marks that user's messages as read, so the inbox `unread_count` becomes `0` for that user. The admin's own messages stay unread for the user.

### Request headers

```http
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

### `GET` example request

```bash
curl "http://127.0.0.1:8000/api/v1/admin/chat/users/1/messages/" \
  -H "Authorization: Bearer <admin_access_token>"
```

### `GET` success response: `200 OK`

The response is the paginated message list shown in endpoint 30, containing both the user's messages and the admin's messages for that user.

### `POST` request

```json
{
  "body": "Thanks, we are checking it now."
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `body` | string | Yes | Non-empty; maximum 2,000 characters |

### `POST` example request

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/chat/users/1/messages/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "Thanks, we are checking it now."
  }'
```

### `POST` success response: `201 Created`

```json
{
  "id": 34,
  "sender": {
    "id": 2,
    "email": "admin@example.com",
    "first_name": "Admin",
    "last_name": "User",
    "balance": "0.00"
  },
  "body": "Thanks, we are checking it now.",
  "created_at": "2026-09-25T11:30:00Z"
}
```

### Error responses

A normal user receives `403 Forbidden`. A staff user ID is not a chat participant, so it returns `404 Not Found`.

```json
{
  "detail": "Not found."
}
```

# Withdrawal API

Users can request an INR payout from their balance to one or more Indian bank accounts. A request holds 1 to 5 payee lines and its `total_amount` is the sum of the payee amounts.

Lifecycle rules:

- A new request is `PENDING` and reserves its total: `available_balance = balance - sum(pending total_amount)`.
- Creating a request never changes `Account.balance`. The reservation is derived from pending requests.
- `confirm` requires a success transaction ID and an amount equal to `total_amount`. It debits the balance and writes a `DEBIT` balance entry.
- `confirm` is idempotent for the same transaction ID and amount, and returns `409 Conflict` for a different one.
- `reject` stores a reason and releases the reservation. Rejected and paid requests cannot be changed again.

References are generated as `WDR-000001` and are unique.

## 34. Get the current user's withdrawal balance

```http
GET /api/v1/withdrawals/balance/
```

### Request headers

```http
Authorization: Bearer <access_token>
```

### Success response: `200 OK`

```json
{
  "balance": "1250.00",
  "pending_amount": "400.00",
  "available_balance": "850.00"
}
```

---

## 35. List the current user's withdrawal requests

```http
GET /api/v1/withdrawals/
```

Newest requests come first and the list is paginated.

### Request headers

```http
Authorization: Bearer <access_token>
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 4,
      "reference": "WDR-000004",
      "total_amount": "400.00",
      "status": "PENDING",
      "note": "Monthly payouts",
      "payees": [
        {
          "id": 5,
          "payee_name": "Ravi Kumar",
          "account_number": "123456789012",
          "ifsc": "HDFC0001234",
          "amount": "250.00",
          "position": 0
        },
        {
          "id": 6,
          "payee_name": "Anita Sharma",
          "account_number": "987654321098",
          "ifsc": "SBIN0004321",
          "amount": "150.00",
          "position": 1
        }
      ],
      "payee_count": 2,
      "paid_transaction_id": "",
      "paid_amount": null,
      "rejection_reason": "",
      "processed_at": null,
      "created_at": "2026-09-27T05:00:00Z",
      "updated_at": "2026-09-27T05:00:00Z"
    }
  ]
}
```

---

## 36. Create a withdrawal request

```http
POST /api/v1/withdrawals/
```

### Request

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/withdrawals/" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
        "note": "Monthly payouts",
        "payees": [
          {
            "payee_name": "Ravi Kumar",
            "account_number": "123456789012",
            "ifsc": "HDFC0001234",
            "amount": "250.00"
          },
          {
            "payee_name": "Anita Sharma",
            "account_number": "987654321098",
            "ifsc": "SBIN0004321",
            "amount": "150.00"
          }
        ]
      }'
```

Field rules:

| Field | Rules |
|---|---|
| `note` | Optional, max 2,000 characters |
| `payees` | 1 to 5 items |
| `payees[].payee_name` | Required, 2 to 100 characters |
| `payees[].account_number` | 6 to 34 digits, unique inside the request |
| `payees[].ifsc` | `ABCD0123456` pattern, normalized to uppercase |
| `payees[].amount` | Greater than `0.01`, at most 2 decimal places |

### Success response: `201 Created`

The response body is the created withdrawal with the same shape as item 35, including the generated `reference`.

### Insufficient available balance: `400 Bad Request`

```json
{
  "detail": "This request is higher than your available balance."
}
```

### Validation error: `400 Bad Request`

```json
{
  "payees": ["Enter a valid IFSC code in the format ABCD0123456."]
}
```

---

## 37. Get one owned withdrawal request

```http
GET /api/v1/withdrawals/{id}/
```

Another user's withdrawal returns `404 Not Found`.

### Success response: `200 OK`

Returns the withdrawal in the same shape as item 35.

---

## 38. List and filter all withdrawal requests

```http
GET /api/v1/admin/withdrawals/
```

### Query parameters

| Parameter | Description |
|---|---|
| `status` | `PENDING`, `PAID`, or `REJECTED` |
| `user_id` | Filter by owner ID |
| `search` | Matches reference, owner email, payee name, account number, or IFSC |
| `page` | Page number |

### Request headers

```http
Authorization: Bearer <admin_access_token>
```

### Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 4,
      "reference": "WDR-000004",
      "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "balance": "850.00"
      },
      "total_amount": "400.00",
      "status": "PENDING",
      "note": "Monthly payouts",
      "payees": [
        {
          "id": 5,
          "payee_name": "Ravi Kumar",
          "account_number": "123456789012",
          "ifsc": "HDFC0001234",
          "amount": "250.00",
          "position": 0
        }
      ],
      "payee_count": 1,
      "paid_transaction_id": "",
      "paid_amount": null,
      "rejection_reason": "",
      "processed_by": null,
      "processed_at": null,
      "created_at": "2026-09-27T05:00:00Z",
      "updated_at": "2026-09-27T05:00:00Z"
    }
  ]
}
```

An invalid `status` value returns `400 Bad Request`.

---

## 39. Get any withdrawal request as admin

```http
GET /api/v1/admin/withdrawals/{id}/
```

### Success response: `200 OK`

Returns the admin shape shown in item 38.

---

## 40. Confirm a withdrawal payout

```http
POST /api/v1/admin/withdrawals/{id}/confirm/
```

Debits the user balance by `amount`, marks the request `PAID`, and writes a `DEBIT` balance entry. Only `PENDING` requests can be confirmed.

### Request

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/withdrawals/4/confirm/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "NEFT9001234", "amount": "400.00"}'
```

### Success response: `200 OK`

The confirmed withdrawal is returned, with `status` set to `PAID`, `paid_transaction_id` and `paid_amount` stored, and `processed_by` set to the admin.

Repeating the same confirmation returns `200 OK` without a second debit.

### Amount or transaction mismatch: `409 Conflict`

```json
{
  "detail": "The confirmed amount must match the requested total."
}
```

### Already processed: `400 Bad Request`

```json
{
  "detail": "Only pending withdrawals can be confirmed."
}
```

---

## 41. Reject a withdrawal request

```http
POST /api/v1/admin/withdrawals/{id}/reject/
```

Stores the reason, releases the reserved amount, and leaves the balance unchanged. Only `PENDING` requests can be rejected.

### Request

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/withdrawals/4/reject/" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "IFSC code is invalid, please resubmit."}'
```

### Success response: `200 OK`

The rejected withdrawal is returned, with `status` set to `REJECTED` and `rejection_reason` stored.

### Missing reason: `400 Bad Request`

```json
{
  "reason": ["This field is required."]
}
```

---

## 42. Get the withdrawal summary as admin

```http
GET /api/v1/admin/withdrawals/summary/
```

A deliberately small endpoint for cheap change detection. It returns aggregate counts and a
change watermark, so a client can refetch the full list only after something actually moved
instead of reloading the paginated list every time. The admin console calls it once on page load
and again when the tab regains focus, so an idle page issues no requests.

It accepts the same `status`, `user_id`, and `search` parameters as endpoint 38, and all values
are scoped to that filter. Calling it with no parameters returns platform-wide totals, which makes
`pending_count` suitable for a navigation badge.

### Request headers

```http
Authorization: Bearer <admin_access_token>
```

### Request

```bash
curl "http://127.0.0.1:8000/api/v1/admin/withdrawals/summary/" \
  -H "Authorization: Bearer <admin_access_token>"

curl "http://127.0.0.1:8000/api/v1/admin/withdrawals/summary/?status=PENDING" \
  -H "Authorization: Bearer <admin_access_token>"
```

### Success response: `200 OK`

```json
{
  "count": 12,
  "pending_count": 3,
  "latest_id": 4,
  "latest_created_at": "2026-09-27T05:00:00Z",
  "latest_processed_at": "2026-09-27T05:04:00Z"
}
```

| Field | Description |
|---|---|
| `count` | Number of withdrawals matching the filter |
| `pending_count` | How many of those are still `PENDING` |
| `latest_id` | ID of the most recently created matching withdrawal, or `null` when there are none |
| `latest_created_at` | Creation time of that withdrawal, or `null` |
| `latest_processed_at` | Most recent confirmation or rejection time, or `null` |

### Detecting changes

Compare the whole payload against the previous response. Any user-visible change moves at least
one field:

| Change | Fields that move |
|---|---|
| New withdrawal created | `count`, `latest_id`, `latest_created_at`, `pending_count` |
| Withdrawal confirmed or rejected | `pending_count`, `latest_processed_at` |

Treat the first response, and any response after the filter parameters change, as a new baseline
rather than a change.

An invalid `status` or `user_id` value returns `400 Bad Request`. A normal user receives
`403 Forbidden`.

---

# Common Error Responses

## Missing or invalid access token: `401 Unauthorized`

```json
{
  "detail": "Authentication credentials were not provided."
}
```

## Normal user using an admin endpoint: `403 Forbidden`

```json
{
  "detail": "You do not have permission to perform this action."
}
```

## Resource not found or not owned by the user: `404 Not Found`

```json
{
  "detail": "Not found."
}
```

## Request throttled: `429 Too Many Requests`

```json
{
  "detail": "Request was throttled. Expected available in 60 seconds."
}
```

## Validation error: `400 Bad Request`

Validation errors are returned under the invalid field:

```json
{
  "text": [
    "This field may not be blank."
  ]
}
```

# Complete User Workflow

1. Register with `POST /api/v1/auth/register/`.
2. Store the returned `access` and `refresh` tokens.
3. Get active requests from `GET /api/v1/payment-requests/`.
4. Download the QR through the returned protected `qr_image_url`.
5. Submit `screenshot` and `text` to `POST /api/v1/payment-requests/{id}/submissions/`; include `proposed_amount` when the request has no fixed amount.
6. Track status with `GET /api/v1/submissions/` and read `proposed_amount`.
7. If declined, read `decline_reason` and submit a new attempt.
8. When accepted, use `final_amount` as the credited amount and view it in `GET /api/v1/balance-history/` or `GET /api/v1/dashboard/`.
9. Refresh the access token before it expires.
10. Send the refresh token to `POST /api/v1/auth/logout/` when signing out.
11. Ask a question with `POST /api/v1/chat/messages/`, then read replies with `GET /api/v1/chat/messages/` and check `unread_count` with `GET /api/v1/chat/`.
12. Check `GET /api/v1/withdrawals/balance/` for `available_balance`, then request an INR payout with `POST /api/v1/withdrawals/` and up to 5 payees.
13. Track the request with `GET /api/v1/withdrawals/`; a confirmed payout appears as a `DEBIT` row in `GET /api/v1/balance-history/`.

# Complete Admin Workflow

1. Create the admin with `python manage.py createsuperuser`.
2. Log in through `POST /api/v1/auth/token/`.
3. Create a request with `POST /api/v1/admin/payment-requests/`.
4. Review pending submissions with `GET /api/v1/admin/submissions/?status=PENDING`.
5. Open `screenshot_url` with the admin access token to inspect the image.
6. Decline with a reason, or accept with `POST /api/v1/admin/submissions/{id}/accept/` and an explicit `final_amount`.
7. Accepted submissions credit the appropriate user's balance using `final_amount`; the same submission cannot be credited twice.
8. Close a completed request with `PATCH /api/v1/admin/payment-requests/{id}/`.
9. Delete an unused request with `DELETE /api/v1/admin/payment-requests/{id}/`; use the force-delete endpoint only when the dependent records must also be removed.
10. Answer user questions from `GET /api/v1/admin/chat/conversations/`, open a thread with `GET /api/v1/admin/chat/users/{id}/messages/`, and reply with `POST /api/v1/admin/chat/users/{id}/messages/`.
11. Review payouts with `GET /api/v1/admin/withdrawals/?status=PENDING`, copy the payee bank details, then confirm with `POST /api/v1/admin/withdrawals/{id}/confirm/` or reject with a reason.
12. Confirmed payouts debit the user balance and are recorded as `DEBIT` rows in `GET /api/v1/admin/balance-history/`.

# Rate Limits

| Scope | Limit |
|---|---|
| Anonymous requests | 60 per minute |
| Authenticated user requests | 300 per minute |
| Registration | 10 per hour |
| Login | 10 per minute |

Rate limits are based on the active throttle configuration in `backend/config/settings.py`.
