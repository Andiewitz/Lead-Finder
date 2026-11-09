import argparse
import contextlib
import io
import json
from unittest.mock import patch
from src import main


def test_find_leads_uses_requested_search_and_does_not_send(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', str(tmp_path / 'leads.db'))
    monkeypatch.setattr(main, 'SEARCH_API_KEY', 'test')
    main.db.init_db(main.DB_PATH)
    candidate = {'title': 'Example', 'url': 'https://example.com', 'content': 'hello@example.com'}
    out = io.StringIO()
    with patch.object(main.discovery, 'discover_leads', return_value=[candidate]) as find, \
         patch.object(main.sender, 'send_email') as send, contextlib.redirect_stdout(out):
        main.cmd_find_leads(argparse.Namespace(industry='plumber', location='Seattle', count=2))
    find.assert_called_once_with('plumber', 'Seattle', main.SEARCH_API_URL, 'test', count=2)
    send.assert_not_called()
    lead = json.loads(out.getvalue())['leads'][0]
    assert lead['location'] == 'Seattle'
    assert lead['qualification_status'] == 'needs review'
