# Automated Cold Emails (Maximally)

Tiny Python automation to send personalized emails from a CSV and a text template.

Repo: https://github.com/muffin-deepseek/Automated-Cold-Emails-Maximally.git

## Setup

1. Install Python 3.10+
2. Optional: create a virtual environment
3. Install dependencies:
```bash
python -m pip install -r requirements.txt
```

## Inputs
- CSV: must contain an `email` column; other columns are optional (e.g. `name`).
- Template: plain text file that can include placeholders like `{{name}}`, `{{from_name}}`, `{{from_email}}`, and `{{today}}`.

## Environment (.env)
Create `.env` alongside `main.py` with your SMTP configuration. The script tolerates common encodings.
```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=app_password
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_FROM_NAME=Your Name
SMTP_FROM_EMAIL=you@example.com
```

## Dry run (no emails sent)
```bash
python main.py --csv contacts.csv --template template.txt --subject "Hello {{name}}" --from-name "Your Name" --from-email you@example.com --dry-run -v
```

## Send for real
```bash
python main.py --csv contacts.csv --template template.txt --subject "Hello {{name}}" --from-name "Your Name" --from-email you@example.com -v
```

## Notes
- Use double quotes around arguments containing braces on Windows.
- Rate limiting: `--rate-limit 1.5`
- Limit rows: `--test-limit 10`
- Log to file: `--log-file send.log`

## License
MIT 