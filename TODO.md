# Kurtex CRM Case Management Updates - Implementation TODO

## Status: [0/14] In Progress

### Phase 1: Dependencies & Backend Setup [0/3]
- [x] Update requirements.txt with pandas, openpyxl, dateutil
- [x] Install dependencies: `pip install -r requirements.txt`
- [ ] Verify app starts: `python app.py`

### Phase 2: Backend Changes (app.py) [5/5]
- [x] Remove POST /api/cases (create case)
- [x] Disable PATCH /api/cases/<id> (view-only, 403)
- [x] Enhance /api/cases filters (date_from/to validation)
- [x] New /api/analytics (manager/team_leader only, extended stats/charts data)
- [x] New /api/export (CSV/Excel with filters, pandas)

### Phase 3: Frontend Changes (dashboard.html) [0/5]
- [ ] Remove all create case UI (buttons, drawer, JS)
- [ ] Disable edit UI in case drawer (status/notes readonly)
- [ ] Add date pickers to Cases tab toolbar
- [ ] New 'Analytics' tab (role-restricted, stats/charts/exports)
- [ ] New 'My Performance' tab (auto-filter user cases, enhanced details)

### Phase 4: UI Enhancements & Polish [0/1]
- [ ] Add Chart.js CDN, basic pie/line charts in Analytics

## Next Step
Run `pip install -r requirements.txt` after Phase 1.

**Updated after each step.**
