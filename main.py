import argparse
import csv
import logging
import os
import smtplib
import ssl
import sys
import time
from datetime import date
from email.message import EmailMessage

from dotenv import load_dotenv


def configure_logging(verbosity: int) -> None:
	level = logging.WARNING
	if verbosity == 1:
		level = logging.INFO
	elif verbosity >= 2:
		level = logging.DEBUG
	logging.basicConfig(
		level=level,
		format="%(asctime)s %(levelname)s %(message)s",
	)


def load_env(env_file: str | None) -> None:
	# Load .env if present or a provided env file, tolerating non-UTF-8 encodings
	path: str | None = None
	if env_file and os.path.exists(env_file):
		path = env_file
	elif os.path.exists('.env'):
		path = '.env'

	if not path:
		return

	# Try common encodings to avoid UnicodeDecodeError on files saved with BOM/UTF-16/etc.
	for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
		try:
			load_dotenv(path, encoding=enc)
			return
		except UnicodeDecodeError:
			continue
		except Exception:
			# Other errors shouldn't block execution; try next encoding
			continue
	logging.warning("Could not read env file '%s' due to encoding issues. Skipping.", path)


def read_template(path: str) -> str:
	with open(path, 'r', encoding='utf-8') as f:
		return f.read()


def render_placeholders(text: str, context: dict[str, str]) -> str:
	# Support {{key}} replacement and a few built-ins
	rendered = text
	# Bring built-ins
	builtins = {
		"today": date.today().isoformat(),
		"from_name": context.get("from_name", ""),
		"from_email": context.get("from_email", ""),
	}
	ctx = {**builtins, **context}
	for key, val in ctx.items():
		if val is None:
			continue
		rendered = rendered.replace(f"{{{{{key}}}}}", str(val))
	return rendered


def read_contacts(csv_path: str) -> list[dict[str, str]]:
	with open(csv_path, newline='', encoding='utf-8') as f:
		reader = csv.DictReader(f)
		rows: list[dict[str, str]] = []
		for row in reader:
			# Normalize keys to lower-case to make placeholders predictable
			rows.append({(k or '').strip().lower(): (v or '').strip() for k, v in row.items()})
		return rows


def build_message(from_name: str, from_email: str, to_email: str, subject: str, body: str) -> EmailMessage:
	msg = EmailMessage()
	if from_name:
		msg["From"] = f"{from_name} <{from_email}>"
	else:
		msg["From"] = from_email
	msg["To"] = to_email
	msg["Subject"] = subject
	msg.set_content(body)
	return msg


def get_smtp_client(host: str, port: int, use_tls: bool, use_ssl: bool, username: str | None, password: str | None):
	if use_ssl:
		context = ssl.create_default_context()
		server = smtplib.SMTP_SSL(host, port, context=context)
	else:
		server = smtplib.SMTP(host, port)
		server.ehlo()
		if use_tls:
			context = ssl.create_default_context()
			server.starttls(context=context)
			server.ehlo()
	if username and password:
		server.login(username, password)
	return server


def parse_bool(val: str | None, default: bool) -> bool:
	if val is None:
		return default
	v = val.strip().lower()
	return v in {"1", "true", "yes", "y", "on"}


def main() -> int:
	parser = argparse.ArgumentParser(description="Send personalized cold emails for Maximally.")
	parser.add_argument("--csv", required=True, help="Path to contacts CSV with an 'email' column.")
	parser.add_argument("--template", required=True, help="Path to email body template file.")
	parser.add_argument("--subject", required=True, help="Email subject (supports {{placeholders}}).")
	parser.add_argument("--from-name", dest="from_name", default=os.getenv("SMTP_FROM_NAME", ""), help="From display name.")
	parser.add_argument("--from-email", dest="from_email", default=os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USERNAME", "")), help="From email address.")
	parser.add_argument("--env-file", dest="env_file", default=None, help="Optional path to .env file.")
	parser.add_argument("--rate-limit", type=float, default=0.0, help="Seconds to sleep between sends.")
	parser.add_argument("--test-limit", type=int, default=0, help="Limit number of rows to process (0 = all).")
	parser.add_argument("--dry-run", action="store_true", help="Do not send, just print what would be sent.")
	parser.add_argument("--log-file", default="", help="Optional path to write a log file.")
	parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv).")

	args = parser.parse_args()

	load_env(args.env_file)
	configure_logging(args.verbose)

	if args.log_file:
		# Add file handler
		fh = logging.FileHandler(args.log_file, encoding='utf-8')
		fh.setLevel(logging.DEBUG)
		fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
		logging.getLogger().addHandler(fh)

	# SMTP settings
	host = os.getenv("SMTP_HOST", "").strip()
	try:
		port = int(os.getenv("SMTP_PORT", "587"))
	except ValueError:
		port = 587
	username = os.getenv("SMTP_USERNAME", "").strip() or None
	password = os.getenv("SMTP_PASSWORD", "").strip() or None
	use_tls = parse_bool(os.getenv("SMTP_USE_TLS", "true"), True)
	use_ssl = parse_bool(os.getenv("SMTP_USE_SSL", "false"), False)

	if not args.dry_run:
		if not host:
			logging.error("SMTP_HOST is required. Set it via env or .env file.")
			return 2
		if not args.from_email:
			logging.error("--from-email or SMTP_FROM_EMAIL/SMTP_USERNAME is required.")
			return 2

	contacts = read_contacts(args.csv)
	if not contacts:
		logging.warning("No contacts found in CSV.")
		return 0

	template_body = read_template(args.template)

	processed = 0
	server = None
	try:
		if not args.dry_run:
			server = get_smtp_client(host, port, use_tls, use_ssl, username, password)

		for row in contacts:
			to_email = row.get("email", "").strip()
			if not to_email:
				logging.warning("Skipping row without email: %s", row)
				continue

			context = {
				**row,
				"from_name": args.from_name or os.getenv("SMTP_FROM_NAME", ""),
				"from_email": args.from_email,
			}

			subject = render_placeholders(args.subject, context)
			body = render_placeholders(template_body, context)

			if args.dry_run:
				print("\n--- DRY RUN ---")
				print(f"To: {to_email}")
				print(f"Subject: {subject}")
				print(body)
			else:
				try:
					msg = build_message(args.from_name, args.from_email, to_email, subject, body)
					assert server is not None
					server.send_message(msg)
					logging.info("Sent to %s", to_email)
				except Exception as e:
					logging.error("Failed to send to %s: %s", to_email, e)

			processed += 1
			if args.test_limit and processed >= args.test_limit:
				logging.info("Test limit reached (%d). Stopping.", args.test_limit)
				break

			if not args.dry_run and args.rate_limit and processed < len(contacts):
				time.sleep(args.rate_limit)
	finally:
		if server is not None:
			try:
				server.quit()
			except Exception:
				pass

	return 0


if __name__ == "__main__":
	sys.exit(main()) 