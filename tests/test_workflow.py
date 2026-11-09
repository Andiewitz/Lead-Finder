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


def test_send_reservation_enforces_suppression_and_quota(tmp_path):
    import pytest

    from src import db
    path = str(tmp_path / 'reserve.db')
    db.init_db(path)
    db.add_to_blacklist('Example.COM', db_path=path)
    with pytest.raises(ValueError, match='do-not-contact'):
        db.reserve_send({'public_business_email': 'person@example.com'}, 2, path)
    first = db.reserve_send({'public_business_email': 'A@other.com'}, 1, path)
    with pytest.raises(ValueError, match='already'):
        db.reserve_send({'public_business_email': 'a@OTHER.com'}, 2, path)
    with pytest.raises(ValueError, match='limit'):
        db.reserve_send({'public_business_email': 'b@other.com'}, 1, path)
    db.mark_sent(first, db_path=path)
    assert db.get_stats(path)['sent_today'] == 1


def test_reply_poll_suppresses_known_sender_once(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from src import db
    path = str(tmp_path / 'replies.db')
    monkeypatch.setattr(main, 'DB_PATH', path)
    monkeypatch.setattr(main, 'IMAP_USER', 'me@example.com')
    monkeypatch.setattr(main, 'IMAP_PASS', 'test')
    monkeypatch.setattr(main, 'OPENROUTER_API_KEY', None)
    db.init_db(path)
    lead_id = db.add_lead_record({'public_business_email': 'lead@example.com'}, db_path=path)
    db.mark_sent(lead_id, db_path=path)
    mail = MagicMock()
    message = b'From: Lead <lead@example.com>\r\nMessage-ID: <one@example.com>\r\nSubject: Re: Hello\r\n\r\nPlease unsubscribe me.'
    mail.uid.side_effect = lambda command, *args: ('OK', [b'1']) if command == 'search' else ('OK', [(b'1', message)])
    with patch('imaplib.IMAP4_SSL', return_value=mail), contextlib.redirect_stdout(io.StringIO()) as out:
        main.cmd_check_replies()
        main.cmd_check_replies()
    assert db.is_blacklisted('LEAD@example.com', path)
    assert '"suppressed": true' in out.getvalue()
    assert '"count": 0' in out.getvalue()


def test_ai_not_interested_is_not_classed_as_interested():
    from src import classifier
    response = {'choices': [{'message': {'content': 'Not interested'}}]}
    with patch('src.classifier.requests.post') as post:
        post.return_value.json.return_value = response
        assert classifier._classify_with_ai('no', 'key') == 'Not interested'


def test_mcp_tool_returns_protocol_content(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, LEAD_FINDER_PYTHON=sys.executable, DB_PATH=str(tmp_path / 'mcp.db'))
    requests = '\n'.join(json.dumps(x) for x in [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'get_stats', 'arguments': {}}},
    ]) + '\n'
    proc = subprocess.run(['node', str(root / 'src' / 'mcp_server.js')], input=requests,
                          text=True, capture_output=True, env=env, timeout=15, check=True)
    messages = [json.loads(line) for line in proc.stdout.splitlines()]
    assert len(messages) == 2
    result = next(m['result'] for m in messages if m.get('id') == 2)
    assert result['content'][0]['type'] == 'text'
    assert json.loads(result['content'][0]['text'])['success'] is True


def test_preview_never_sends_or_reserves(tmp_path, monkeypatch):
    path = str(tmp_path / 'preview.db')
    monkeypatch.setattr(main, 'DB_PATH', path)
    monkeypatch.setattr(main, 'FROM_NAME', 'Tester')
    monkeypatch.setattr(main, 'OPENROUTER_API_KEY', None)
    main.db.init_db(path)
    args = argparse.Namespace(email='person@example.com', company='Example', personalization='', category='services', preview=True)
    with patch.object(main.sender, 'send_email') as send, contextlib.redirect_stdout(io.StringIO()) as out:
        main.cmd_send_email(args)
    send.assert_not_called()
    assert json.loads(out.getvalue())['preview'] is True
    assert main.db.get_stats(path)['draft'] == 1
    assert 'github.com/Andiewitz' not in out.getvalue()


def test_uncertain_send_blocks_retry_and_consumes_quota(tmp_path):
    import pytest

    from src import db
    path = str(tmp_path / 'uncertain.db')
    db.init_db(path)
    lead = db.reserve_send({'public_business_email': 'a@example.com'}, 1, path)
    db.mark_send_uncertain(lead, path)
    with pytest.raises(ValueError, match='pending send'):
        db.reserve_send({'public_business_email': 'a@example.com'}, 1, path)
    with pytest.raises(ValueError, match='limit'):
        db.reserve_send({'public_business_email': 'b@example.com'}, 1, path)


def _run_cli(tmp_path, *args, extra_env=None):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for key in ('SEARCH_API_KEY', 'OPENROUTER_API_KEY', 'SMTP_USER', 'SMTP_PASS',
                'FROM_NAME', 'FROM_EMAIL', 'IMAP_USER', 'IMAP_PASS', 'DB_PATH',
                'SMTP_PORT', 'DAILY_LIMIT'):
        env.pop(key, None)
    env.update(LEAD_FINDER_HOME=str(tmp_path), **(extra_env or {}))
    return subprocess.run([sys.executable, str(root / 'src' / 'main.py'), *args],
                          cwd=root, env=env, text=True, capture_output=True, timeout=20)


def test_missing_credentials_only_block_relevant_features(tmp_path):
    status = _run_cli(tmp_path, 'status', extra_env={'SMTP_PORT': 'bad', 'DAILY_LIMIT': 'bad'})
    assert status.returncode == 0
    discovery = _run_cli(tmp_path, 'find-leads')
    assert discovery.returncode != 0 and 'SEARCH_API_KEY' in discovery.stderr
    preview = _run_cli(tmp_path, 'send-email', '--email', 'a@example.com', '--preview')
    assert preview.returncode != 0 and 'FROM_NAME' in preview.stderr
    preview = _run_cli(tmp_path, 'send-email', '--email', 'a@example.com', '--preview',
                       extra_env={'FROM_NAME': 'Tester'})
    assert preview.returncode == 0 and json.loads(preview.stdout)['writer'] == 'template'
    sending = _run_cli(tmp_path, 'send-email', '--email', 'a@example.com',
                       extra_env={'FROM_NAME': 'Tester'})
    assert sending.returncode != 0 and 'SMTP_USER' in sending.stderr
    replies = _run_cli(tmp_path, 'check-replies')
    assert replies.returncode != 0 and 'IMAP not configured' in replies.stdout


def test_config_roundtrip_preserves_special_values_and_environment_precedence(tmp_path):
    import os
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    values = {'FROM_NAME': 'Saved "name"', 'CUSTOM_VALUE': 'C:\\some path\\${variable} # comment',
              'FROM_COMPANY': 'Company #1'}
    env = dict(os.environ, LEAD_FINDER_HOME=str(tmp_path))
    script = "const c=require('./src/config'); let s=''; process.stdin.on('data',x=>s+=x); process.stdin.on('end',()=>{ c.saveEnv(JSON.parse(s)); console.log(JSON.stringify(c.loadExistingEnv())); });"
    proc = subprocess.run(['node', '-e', script], cwd=root, env=env, input=json.dumps(values),
                          text=True, capture_output=True, check=True)
    assert json.loads(proc.stdout) == values
    result = _run_cli(tmp_path, 'send-email', '--email', 'a@example.com', '--preview')
    assert result.returncode == 0
    assert 'Saved "name"' in json.loads(result.stdout)['body']
    result = _run_cli(tmp_path, 'send-email', '--email', 'a@example.com', '--preview',
                      extra_env={'FROM_NAME': 'Environment Name'})
    assert 'Environment Name' in json.loads(result.stdout)['body']


def test_search_authentication_and_network_errors_are_not_empty_results():
    import pytest
    import requests

    from src import discovery
    response = requests.Response()
    response.status_code = 401
    with patch('src.discovery.requests.post') as post:
        post.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
        with pytest.raises(discovery.SearchError, match='rejected'):
            discovery.web_search('query', 'https://example.com', 'invalid')
    with patch('src.discovery.requests.post', side_effect=requests.Timeout):
        with pytest.raises(discovery.SearchError, match='reach Tavily'):
            discovery.web_search('query', 'https://example.com', 'key')


def test_setup_skip_and_existing_keep_preserve_configuration(tmp_path):
    import os
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, LEAD_FINDER_HOME=str(tmp_path))
    script = """
Object.defineProperty(process.stdin, 'isTTY', {value: true});
const key = require.resolve('enquirer');
require.cache[key] = {id:key, filename:key, loaded:true,
  exports:{prompt: async (questions) => Array.isArray(questions) ? {} : {choice: process.argv[1]}}};
require('./src/tui').configWizard().catch(e => {console.error(e); process.exitCode=1});
"""
    first = subprocess.run(['node', '-e', script, 'edit'], cwd=root, env=env,
                           capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert first.returncode == 0
    config = tmp_path / '.env'
    original = config.read_text(encoding='utf8')
    assert 'SEARCH_API_KEY=' not in original
    config.write_text(original + 'CUSTOM_VALUE="unchanged"\n', encoding='utf8')
    original = config.read_text(encoding='utf8')
    keep = subprocess.run(['node', '-e', script, 'keep'], cwd=root, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert keep.returncode == 0
    assert config.read_text(encoding='utf8') == original
    edit = subprocess.run(['node', '-e', script, 'edit'], cwd=root, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert edit.returncode == 0
    assert 'CUSTOM_VALUE="unchanged"' in config.read_text(encoding='utf8')


def test_blacklist_failure_does_not_report_success():
    import sqlite3
    from unittest.mock import MagicMock

    import pytest

    conn = MagicMock()
    conn.execute.side_effect = sqlite3.OperationalError('database locked')
    out = io.StringIO()
    with patch.object(main.db, 'get_connection', return_value=conn), contextlib.redirect_stdout(out):
        with pytest.raises(sqlite3.OperationalError):
            main.cmd_blacklist(argparse.Namespace(email='test@example.com', reason='opt out'))
    assert 'blacklisted' not in out.getvalue()


def test_html_reply_and_common_opt_out_are_processed(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from src import db
    path = str(tmp_path / 'html.db')
    monkeypatch.setattr(main, 'DB_PATH', path)
    monkeypatch.setattr(main, 'IMAP_USER', 'me@example.com')
    monkeypatch.setattr(main, 'IMAP_PASS', 'test')
    monkeypatch.setattr(main, 'OPENROUTER_API_KEY', None)
    db.init_db(path)
    lead = db.add_lead_record({'public_business_email': 'lead@example.com'}, db_path=path)
    db.mark_sent(lead, db_path=path)
    msg = (b'From: lead@example.com\r\nMessage-ID: <html@x>\r\n'
           b'Content-Type: text/html; charset=utf-8\r\n\r\n'
           b'<p>Please take me off your list.</p><blockquote>Earlier text</blockquote>')
    mail = MagicMock()
    mail.uid.side_effect = lambda cmd, *args: ('OK', [b'1']) if cmd == 'search' else ('OK', [(b'1', msg)])
    with patch('imaplib.IMAP4_SSL', return_value=mail), contextlib.redirect_stdout(io.StringIO()):
        main.cmd_check_replies()
    assert db.is_blacklisted('lead@example.com', path)
    mail.uid.assert_any_call('search', None, 'ALL')
    mail.uid.assert_any_call('fetch', b'1', '(BODY.PEEK[])')


def test_unreadable_reply_is_not_marked_processed(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from src import db
    path = str(tmp_path / 'empty.db')
    monkeypatch.setattr(main, 'DB_PATH', path)
    monkeypatch.setattr(main, 'IMAP_USER', 'me@example.com')
    monkeypatch.setattr(main, 'IMAP_PASS', 'test')
    db.init_db(path)
    lead = db.add_lead_record({'public_business_email': 'lead@example.com'}, db_path=path)
    db.mark_sent(lead, db_path=path)
    mail = MagicMock()
    msg = b'From: lead@example.com\r\nMessage-ID: <empty@x>\r\nContent-Type: image/png\r\n\r\nxx'
    mail.uid.side_effect = lambda cmd, *args: ('OK', [b'1']) if cmd == 'search' else ('OK', [(b'1', msg)])
    out = io.StringIO()
    with patch('imaplib.IMAP4_SSL', return_value=mail), contextlib.redirect_stdout(out):
        main.cmd_check_replies()
        main.cmd_check_replies()
    assert out.getvalue().count('Needs review') == 2


def test_saved_preview_sends_exact_content_and_rechecks_suppression(tmp_path, monkeypatch):
    import pytest

    path = str(tmp_path / 'draft.db')
    for key, value in {'DB_PATH': path, 'FROM_NAME': 'Tester', 'OPENROUTER_API_KEY': None,
                       'SMTP_USER': 'me@example.com', 'SMTP_PASS': 'x', 'FROM_EMAIL': 'me@example.com',
                       'SMTP_PORT': '587', 'DAILY_LIMIT': '5'}.items():
        monkeypatch.setattr(main, key, value)
    main.db.init_db(path)
    args = argparse.Namespace(email='person@example.com', company='Example', personalization='verified detail', category='services', preview=True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main.cmd_send_email(args)
    preview = json.loads(out.getvalue())
    main.db.add_to_blacklist('person@example.com', db_path=path)
    with patch.object(main.sender, 'send_email') as send, contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit):
            main.cmd_send_draft(argparse.Namespace(id=preview['draft_id']))
    send.assert_not_called()
    conn = main.db.get_connection(path)
    conn.execute('DELETE FROM blacklist')
    conn.commit()
    conn.close()
    with patch.object(main.sender, 'send_email', return_value=True) as send, contextlib.redirect_stdout(io.StringIO()):
        main.cmd_send_draft(argparse.Namespace(id=preview['draft_id']))
    sent_args = send.call_args.args
    assert sent_args[1] == preview['subject']
    from html import escape
    assert sent_args[2] == '<p>' + escape(preview['body']).replace('\n', '<br>') + '</p>'
    assert main.db.get_draft(preview['draft_id'], path) is None


def test_smtp_outcomes_and_review_resolution(tmp_path):
    import smtplib
    from unittest.mock import MagicMock

    import pytest

    from src import db, sender
    args = ('recipient@example.com', 'subject', 'body', 'smtp.example.com', 587,
            'user', 'password', 'Tester', 'me@example.com')
    server = MagicMock()
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b'failed')
    with patch.object(sender.smtplib, 'SMTP', return_value=server):
        with pytest.raises(sender.DeliveryNotSentError):
            sender.send_email(*args)
    server = MagicMock()
    server.send_message.side_effect = OSError('connection lost')
    with patch.object(sender.smtplib, 'SMTP', return_value=server):
        assert sender.send_email(*args) is False
    server = MagicMock()
    server.quit.side_effect = OSError('quit failed')
    with patch.object(sender.smtplib, 'SMTP', return_value=server):
        assert sender.send_email(*args) is True
    path = str(tmp_path / 'review.db')
    db.init_db(path)
    lead = db.reserve_send({'public_business_email': 'recipient@example.com'}, 5, path)
    db.mark_send_uncertain(lead, path)
    assert db.get_pending_sends(path)[0]['id'] == lead
    assert db.resolve_pending_send(lead, False, path)
    assert db.get_draft(lead, path) is not None
    assert not db.resolve_pending_send(lead, False, path)
