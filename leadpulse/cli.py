import argparse
import asyncio
import sys
from rich.console import Console

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .models import OutreachStatus
from .pipeline import display_leads_table, execute_lead_pulse
from .storage import export_to_csv, get_all_leads, sync_to_google_sheets, update_lead_status

console = Console(legacy_windows=False)



def parse_args():
    parser = argparse.ArgumentParser(
        description="LeadPulse NG - Automated High-Ticket Lead & Bio-Link Auditor"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: collect
    collect_parser = subparsers.add_parser("collect", help="Discover, audit, score and export leads")
    collect_parser.add_argument(
        "--niche", "-n", default=None, help="Target niche (e.g. 'Shortlet', 'Solar', 'Med-Spa')"
    )
    collect_parser.add_argument(
        "--location", "-l", default=None, help="Target location (e.g. 'Lekki Phase 1', 'Ikoyi', 'Wuse 2')"
    )
    collect_parser.add_argument(
        "--limit", type=int, default=20, help="Max candidate leads to fetch per source"
    )
    collect_parser.add_argument(
        "--sweep", action="store_true", help="Run full sweep across all high-ticket Lagos & Abuja categories"
    )

    # Command: test
    subparsers.add_parser("test", help="Verify live pipeline end-to-end on live HTTP search results")

    # Command: export
    export_parser = subparsers.add_parser("export", help="Export stored leads to CSV or Google Sheets")
    export_parser.add_argument(
        "--min-score", type=int, default=0, help="Minimum lead score filter (0-100)"
    )
    export_parser.add_argument(
        "--sheets", action="store_true", help="Sync leads directly to Google Sheets"
    )

    # Command: mark
    mark_parser = subparsers.add_parser("mark", help="Update outreach status for a lead")
    mark_parser.add_argument("query", help="Lead ID or Business Name substring")
    mark_parser.add_argument(
        "status",
        choices=["Pending", "Preview Built", "DM Sent", "Closed"],
        help="New outreach status",
    )

    # Command: view
    subparsers.add_parser("view", help="View stored leads table in terminal")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Launch the mobile PWA web application")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000)")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")

    return parser.parse_args()


def main():
    args = parse_args()
    cmd = args.command or "serve"

    if cmd == "serve":
        import uvicorn
        port = getattr(args, "port", 8000)
        host = getattr(args, "host", "0.0.0.0")
        console.print(f"\n[bold green]📱 Starting LeadPulse NG Mobile PWA on http://localhost:{port}[/bold green]")
        console.print("[dim]To open on your phone, connect to your computer's local Wi-Fi IP (e.g. http://192.168.x.x:8000)[/dim]\n")
        uvicorn.run("server:app", host=host, port=port, reload=False)

    elif cmd == "test":
        # Run a fast, single query test without exhausting Serper credits
        console.print("[bold yellow]🧪 Running quick pipeline test on Lekki Shortlets (limit: 5)...[/bold yellow]")
        leads = asyncio.run(
            execute_lead_pulse(
                niche="Shortlet Apartments",
                location="Lekki Phase 1, Lagos",
                limit=5,
                full_sweep=False,
            )
        )
        display_leads_table(leads)

    elif cmd == "collect":
        full_sweep = getattr(args, "sweep", False) or not getattr(args, "niche", None)
        niche = getattr(args, "niche", None) if not full_sweep else None
        location = getattr(args, "location", None) if not full_sweep else None
        limit = getattr(args, "limit", 20)

        leads = asyncio.run(
            execute_lead_pulse(
                niche=niche,
                location=location,
                limit=limit,
                full_sweep=full_sweep,
            )
        )
        display_leads_table(leads)

    elif cmd == "export":
        csv_file = export_to_csv(min_score=args.min_score)
        console.print(f"[bold green]✓ Successfully exported qualified leads to: {csv_file}[/bold green]")
        if args.sheets:
            success, msg = sync_to_google_sheets()
            console.print(f"[{'green' if success else 'red'}]{msg}[/{'green' if success else 'red'}]")

    elif cmd == "mark":
        updated = update_lead_status(args.query, args.status)
        if updated > 0:
            console.print(f"[bold green]✓ Updated status to '{args.status}' for {updated} lead(s).[/bold green]")
        else:
            console.print(f"[yellow]No leads found matching '{args.query}'.[/yellow]")

    elif cmd == "view":
        leads = get_all_leads()
        if not leads:
            console.print("[yellow]No leads found in database. Run 'collect' or 'test' first![/yellow]")
        else:
            display_leads_table(leads)


if __name__ == "__main__":
    main()
