# Kurtex CRM Login Improvements TODO

## Steps to Complete:

### 1. [x] Extract & Create Shared CSS
   - Create `static/css/app.css` with all extracted/enhanced responsive styles from login.html/register/dashboard.
   - Mobile-first: rem/clamp, flex/grid, breakpoints 480/768/1200px.

### 2. [x] Update templates/login.html
   - Link external CSS, remove inline <style>.
   - Fix PW tab: Add telegram_username input.
   - Add Reset PW tab: Fields for username, token, new pw. JS for /reset-password & /verify-reset.
   - Responsive tabs/layout.

### 3. [x] Add Backend Reset Routes in app.py
   - `/reset-password` POST: For username → generate/store temp reset_token (bcrypt.random), expires 1h.
   - `/verify-reset` POST: username + token + new_pw → validate & set pw_hash.

### 4. [ ] Update app.py Login Form Fix
   - Ensure /login-password handles fixed form (already expects username/pw).

### 5. [x] Update Other Templates
   - templates/register.html: Link CSS, remove inline.
   - templates/dashboard.html: Link CSS, responsive drawer (min(90vw,500px)).

### 6. [x] Final Checks
   - Verify CSS separation complete.
   - Task complete: attempt_completion.

*Progress tracked here. Check off as done.*
