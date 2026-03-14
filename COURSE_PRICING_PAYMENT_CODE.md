# Course Pricing and Payment – Generated Code Reference

This document lists where the plan was implemented. All code is already in the project.

---

## 1. Models (`counselor/models.py`)

- **CounselorCourse**: Added `price` (DecimalField, null/blank, default=0) and `is_free` property.
- **CoursePayment**: user, course, amount, currency, gateway_receipt, gateway_order_id, gateway_payment_id, gateway_signature, is_success, created, updated; `get_gateway_amount()`.
- **PaymentReceipt**: OneToOne to CoursePayment; transaction_id, invoice_number, invoice_pdf, created.

Migration: `counselor/migrations/0017_add_price_and_payment.py`.

---

## 2. Admin (`counselor/admin.py`)

- CounselorCourse: `price` in `list_display`.
- CoursePaymentAdmin and PaymentReceiptAdmin registered.

---

## 3. Razorpay (`counselor/payment/razorpay.py`)

- `RazorpayService`: `create_order()`, `verify_payment()`, `get_signature_status()`, `get_payment_status()`.

Settings: `RAZORPAY_KEY`, `RAZORPAY_SECRET` in `counselor_project/settings.py`.  
Dependency: `razorpay>=1.4.0` in `requirements.txt`.

---

## 4. URLs (`counselor/urls.py`)

- `''` → `landing_view` (name `landing`)
- `'login/'` → `login_view`
- `'course/<str:course_name>/payment/'` → `course_payment_view` (name `course_payment`)
- `'update_counselor_course_payment/'` → `update_counselor_course_payment`
- `'course_payment_success/<path:enc_id>/'` → `course_payment_success_view`
- `'course_payment_fail/<path:enc_id>/'` → `course_payment_fail_view`
- `'receipt/<int:payment_id>/download/'` → `receipt_download_view` (name `receipt_download`)

---

## 5. Views (`counselor/views.py`)

- **landing_view** – Public; courses with price; Login, Signup, Learn More, Start course (→ login with next=payment).
- **user_logout** – Redirects to `counselor:landing`.
- **user_login** – Reads `next` from GET/POST; redirects to `next` after login.
- **icef_view** – Adds `has_paid` and `price` to each course in `course_statuses`.
- **course_overview** – Works for anonymous and logged-in; shows price; Start/Resume → login, payment, or enrolled.
- **course_payment_view** – Login required; free or already paid → redirect to course; else create CoursePayment + Razorpay order; signed success/fail URLs.
- **update_counselor_course_payment** – POST JSON; verify Razorpay; update CoursePayment; create PaymentReceipt on success; return JSON with redirect_url.
- **course_payment_success_view** – Decode enc_id; show payment details, transaction ID, “Download payment”, “Start course”.
- **course_payment_fail_view** – “Retry” button → payment page.
- **receipt_download_view** – Serve PDF or generate HTML receipt; owner + is_success check.

Helpers: `_payment_enc_id()`, `_payment_from_enc_id()`.

---

## 6. Enrolled Course Gate (`counselor/views_v2.py`)

- **CounselorEnrolledCourseViewV2** and **FetchCurrentPartViewV2**: After resolving user/course, if `course.price > 0` and no successful CoursePayment for that user/course, redirect to `counselor:course_payment` for that course_name.

---

## 7. Templates

| File | Purpose |
|------|---------|
| `templates/landing.html` | Public landing; course cards with price; Login, Signup, Learn More, Start course |
| `templates/course_payment.html` | Razorpay checkout; Pay button; POST to update endpoint; redirect on success/fail |
| `templates/course_payment_success.html` | Summary, transaction ID, “Download payment”, “Start course” |
| `templates/course_payment_fail.html` | Message and “Retry” button |
| `templates/receipt_pdf.html` | HTML used for receipt download |
| `templates/login.html` | Hidden `next` input; form posts to user_login |
| `templates/icef-course.html` | Per-course price; Start Now → payment when not paid and price > 0 |
| `templates/course-overview.html` | Price; Start/Resume → login / payment / enrolled by has_paid and is_anonymous |

---

## 8. Flow Summary

1. Open project → **landing** (public) with courses and pricing.
2. **Learn More** → course overview (with price); **Start course** → login (with next=payment) or payment or enrolled.
3. **Start Now** (from list or overview) → payment page if not paid and price > 0; else enrolled course.
4. Payment page → Razorpay; on success → success page (details, transaction ID, download receipt, Start course); on fail → fail page with Retry.
5. Enrolled course URLs require successful payment (or free course).

---

## 9. Setup

1. Run migrations: `python manage.py migrate`
2. Set in env: `RAZORPAY_KEY`, `RAZORPAY_SECRET`
3. In Django Admin, set **price** for each course (0 or blank = free)
