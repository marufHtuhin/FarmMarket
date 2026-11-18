# API and Demo Notes

Base path: `/api/v1` (full table in the root README; interactive docs at `/docs`).

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | Public | Create farmer/buyer/transporter account |
| POST | `/auth/login` | Public | Get access + refresh JWTs |
| POST | `/auth/refresh` | Refresh token | Rotate tokens (reuse revokes all) |
| POST | `/auth/logout` | JWT | Revoke refresh token |
| POST | `/auth/forgot-password` / `/auth/reset-password` | Public | Password reset flow |
| GET | `/auth/me` | JWT | Current account |
| GET | `/countries` / `/crops` | Public | Markets with hubs; crop catalogue |
| GET | `/transporters` | Public | Transporter directory (no contact details) |
| GET/POST | `/farms` | Farmer | Own farms / create farm |
| GET/POST | `/products` | Public/Farmer | Browse/list products |
| POST | `/products/{id}/images` | Farmer owner | Upload up to 5 photos |
| PUT/DELETE | `/products/{id}` | Farmer owner | Edit/remove own product |
| GET/POST | `/demands` | JWT/Buyer | Browse own demand or create demand |
| GET | `/matches` | JWT | Calculate matching recommendations |
| GET | `/prices` | Public | Browse reference price records |
| POST | `/prices/manual` | Admin | Enter a daily market price (source + timestamp stored) |
| GET | `/prices/manual` | Admin | Recent manual price entries |
| GET | `/prices/latest` | Public | Latest price per hub × crop (source + REAL/DEMO label) |
| GET | `/weather/{hub}` | Public | Open-Meteo past 7d + current + next 7d (no key needed) |
| POST | `/conversations` | Farmer/buyer | Create-or-find a chat with the other party |
| GET | `/conversations` | Farmer/buyer | My chats (unread counts + last message) |
| GET | `/conversations/{id}/messages` | Participant | Thread messages |
| POST | `/conversations/{id}/messages` | Participant | Send a message (rate-limited) |
| POST | `/conversations/{id}/read` | Participant | Mark thread read |
| POST | `/offers` | Buyer | Make an offer on a listing |
| GET | `/offers/my` | JWT | Own offers (incoming for farmers) |
| PATCH | `/offers/{id}` | Farmer owner | Accept (creates order) / reject / cancel |
| POST | `/orders` | Buyer | Place order |
| GET | `/orders/my` | JWT | View own orders |
| GET | `/orders/{id}` | Order party | Order detail |
| PATCH | `/orders/{id}/status` | Order owner | Accept/reject/complete/cancel |
| PATCH | `/orders/{id}/assign` | Farmer/admin | Assign a transporter |
| GET/PATCH | `/deliveries` / `/deliveries/{order_id}` | Transporter | Deliveries + status updates |
| GET/POST | `/vehicles` | Transporter | Vehicle management |
| POST | `/assistant/chat` | JWT | Krishi Bondhu chat (Gemini+RAG or template) |
| POST | `/assistant/chat/stream` | JWT | Streaming chat (SSE tokens; template fallback instant) |
| POST | `/assistant/test` | Admin | One tiny live Gemini probe: ok/mode/latency/error (never the key) |
| GET | `/assistant/status` | Admin | Gemini diagnostics: key configured, model, last error (never the key) |
| POST | `/logistics/plan` / `/logistics/optimize` | JWT | Heuristic plan / OR-Tools VRP |
| GET | `/twin/batches/{code}/qr` | Public | Batch QR code (PNG) |
| GET | `/twin/batches/{code}/alerts` | Farmer/admin | Threshold alerts |
| GET | `/admin/stats` / `/admin/users` / `/admin/data-sources` | Admin | Admin tools |
| GET | `/notifications` | JWT | View notifications |
| GET | `/dashboard` | JWT | Role-based dashboard summary |

## Matching weights
- Product: 30%
- Quantity: 25%
- Location: 20%
- Price: 15%
- Time: 10%

The score is an explainable heuristic for a hackathon prototype. It is not a trained predictive model and should not be described as one.

## Demo sequence
1. Login as buyer (`buyer@farmmarket.demo`, `Demo123!`) and post demand.
2. Login as farmer (`farmer@farmmarket.demo`, `Demo123!`) and list matching produce.
3. Open AI Matches and explain the component scores.
4. Login as buyer, open the listing and make an offer (or place a direct order).
5. Login as farmer, accept the offer from Offers (an order is created), then
   assign the demo transporter from the order detail page.
6. Login as transporter (`transporter@farmmarket.demo`, `Demo123!`) and move
   the delivery through picked up → in transit → delivered.

Seeded market prices are labelled illustrative. Replace them with verified market observations and cite the source, market, unit and date in any public demo.

## Order state rules

- A buyer can cancel an order only while it is `pending`.
- A farmer can accept or reject an order only while it is `pending`.
- A farmer can mark an order `completed` only after it has been accepted.
- The requested stock is reserved when the order is placed. If a pending order is rejected or cancelled, the reserved quantity is returned to the listing.

## Local quick start

The default database is SQLite. From `backend`, install `requirements.txt`, copy `.env.example` to `.env`, run `python seed_demo.py`, then `uvicorn app.main:app --reload`. See the root README for the MySQL alternative and production cautions.
