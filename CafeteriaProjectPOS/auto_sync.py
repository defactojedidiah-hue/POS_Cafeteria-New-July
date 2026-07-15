"""
auto_sync.py — Background auto-sync watcher for ISUFST Cafeteria POS
Watches for internet, syncs pending SQLite transactions to Firestore.
Reads auto_sync setting from backup_settings.json
"""
import threading
import time
import json
import os

_stop_event  = threading.Event()
_sync_thread = None
_SETTINGS    = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "backup_settings.json")


def _load_settings():
    try:
        with open(_SETTINGS) as f:
            return json.load(f)
    except Exception:
        return {"auto_sync": True, "auto_backup": False}


def _watcher(store):
    """Background thread — checks every 30s, syncs if internet + auto_sync ON."""
    import database as db
    import offline_db

    last_online = False
    print(f"[AutoSync] Watcher started for store={store}")

    while not _stop_event.is_set():
        try:
            s      = _load_settings()
            online = db.has_internet()

            if s.get("auto_sync", True) and online:
                # Sync any pending transactions
                pending = offline_db.get_pending_transactions()
                if pending:
                    print(f"[AutoSync] {len(pending)} pending txn(s) — syncing...")
                    synced = 0
                    for txn in pending:
                        try:
                            db.upload_offline_transaction_to_firestore(txn)
                            offline_db.mark_transaction_synced(txn["txn_id"])
                            synced += 1
                        except Exception as e:
                            offline_db.mark_transaction_failed(txn["txn_id"], str(e))
                            print(f"[AutoSync] Sync error for {txn['txn_id']}: {e}")
                    if synced:
                        print(f"[AutoSync] ✅ Synced {synced} transaction(s).")

            if not last_online and online:
                print("[AutoSync] 🌐 Internet detected.")
            elif last_online and not online:
                print("[AutoSync] 📴 Internet lost — saving locally.")

            last_online = online

        except Exception as e:
            print(f"[AutoSync] Watcher error: {e}")

        # Wait 30 seconds before next check
        _stop_event.wait(30)

    print("[AutoSync] Watcher stopped.")


def start(store="cafestore"):
    """Start the background auto-sync watcher."""
    global _sync_thread, _stop_event
    _stop_event.clear()
    _sync_thread = threading.Thread(target=_watcher, args=(store,), daemon=True)
    _sync_thread.start()


def stop():
    """Stop the background watcher."""
    _stop_event.set()