"""變異測試（mutation testing）執行器。

為何不直接用 mutmut：mutmut 3 會跳過「帶裝飾器的函式」與「模組 / 類別層程式碼」，
在 Django 專案等於跳過所有 @router API 端點、@login_required view、pydantic validator、
@property，以及 Schema / Model 欄位與常數。本工具沿用 mutmut 3.8 的節點運算子，
但對整個檔案（含上述部分）產生變異，另補四種運算子：

- decorator_remove：逐一移除函式上的裝飾器
- stmt_delete：刪除「純呼叫」語句與 del 語句
- if_negate：if / elif / while 條件整個反轉
- return_none：return <expr> 改為 return None

不變異：import、型別註記、docstring、logger.* 呼叫（同 PIT 預設避開 logging）、
len() / isinstance()（同 mutmut）。

執行方式（詳見 scripts/mutation/README.md）：

    pip install mutmut==3.8.0
    python scripts/mutation/mutation_test.py run --workers 8
    python scripts/mutation/mutation_test.py report --out <run 輸出目錄>

每個 worker 是一份獨立的專案副本，使用獨立的 Postgres 測試庫（POSTGRES_DB=mut_w{i}，
pytest-django 會建立 test_mut_w{i}，並以 --reuse-db 重複使用）。
函式主體內的變異只跑 coverage context 顯示「有執行到該行」的測試；
模組 / 類別層變異（import 時就生效）一律跑全套。最後再以全套測試複驗所有存活者，
排除測試挑選造成的假存活。
"""

import argparse
import difflib
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TARGETS = [
    'shortener/analytics.py',
    'shortener/api.py',
    'shortener/auth.py',
    'shortener/models.py',
    'shortener/og_parser.py',
    'shortener/ownership.py',
    'shortener/qr_utils.py',
    'shortener/services.py',
    'shortener/utils.py',
    'shortener/validators.py',
    'shortener/views.py',
    'shortener/templatetags/short_urls.py',
    'ninja_shortener/api.py',
    'ninja_shortener/urls.py',
]

# 變異測試專用設定：只把密碼雜湊換成 MD5 加速 create_user（不影響被測邏輯）
MUTATION_SETTINGS = '''from ninja_shortener.settings import *  # noqa: F401,F403

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
'''

COPY_EXCLUDES = {'.git', 'node_modules', '__pycache__', 'htmlcov', '.coverage', 'staticfiles'}


# =============================================================================
# 產生變異體
# =============================================================================


def generate_mutants(out_dir, targets):
    import libcst as cst
    import libcst.matchers as m
    from libcst.metadata import ParentNodeProvider, PositionProvider
    from mutmut.mutation.mutators import mutation_operators

    never_mutate_calls = {'len', 'isinstance'}
    logger_names = {'logger', 'logging'}

    def is_docstring_stmt(node):
        return (
            isinstance(node, cst.SimpleStatementLine)
            and len(node.body) == 1
            and isinstance(node.body[0], cst.Expr)
            and isinstance(node.body[0].value, (cst.SimpleString, cst.ConcatenatedString))
        )

    def is_logger_call(node):
        return (
            isinstance(node, cst.Call)
            and isinstance(node.func, cst.Attribute)
            and isinstance(node.func.value, cst.Name)
            and node.func.value.value in logger_names
        )

    def skip_subtree(node):
        if isinstance(node, (cst.Import, cst.ImportFrom, cst.Annotation)):
            return True
        if is_docstring_stmt(node) or is_logger_call(node):
            return True
        if isinstance(node, cst.Call) and isinstance(node.func, cst.Name) and node.func.value in never_mutate_calls:
            return True
        return (
            isinstance(node, cst.SimpleStatementLine)
            and len(node.body) == 1
            and isinstance(node.body[0], cst.Expr)
            and is_logger_call(node.body[0].value)
        )

    def op_stmt_delete(node):
        if len(node.body) != 1:
            return
        stmt = node.body[0]
        if isinstance(stmt, cst.Del) or (isinstance(stmt, cst.Expr) and isinstance(stmt.value, cst.Call)):
            yield node.with_changes(body=[cst.Pass()])

    def op_if_negate(node):
        if isinstance(node, (cst.If, cst.While)):
            test = node.test.with_changes(lpar=[cst.LeftParen()], rpar=[cst.RightParen()])
            yield node.with_changes(test=cst.UnaryOperation(operator=cst.Not(), expression=test))

    def op_return_none(node):
        if node.value is not None and not m.matches(node.value, m.Name('None')):
            yield node.with_changes(value=cst.Name('None'))

    def op_decorator_remove(node):
        for i in range(len(node.decorators)):
            yield node.with_changes(decorators=[*node.decorators[:i], *node.decorators[i + 1:]])

    operators = [(t, f, f.__name__.replace('operator_', '')) for t, f in mutation_operators] + [
        (cst.SimpleStatementLine, op_stmt_delete, 'stmt_delete'),
        (cst.CSTNode, op_if_negate, 'if_negate'),
        (cst.Return, op_return_none, 'return_none'),
        (cst.FunctionDef, op_decorator_remove, 'decorator_remove'),
    ]

    class Collector(cst.CSTVisitor):
        def __init__(self):
            self.candidates = []

        def on_visit(self, node):
            if skip_subtree(node):
                return False
            for node_type, op, name in operators:
                if isinstance(node, node_type):
                    for mutated in op(node):
                        self.candidates.append((node, mutated, name))
            return True

    def scope_of(node, parents):
        """節點在函式主體內（呼叫時才執行）→ ('function', 名稱)；否則為定義 / import 時執行。"""
        child, cur = node, parents.get(node)
        while cur is not None:
            if isinstance(cur, cst.Lambda) and child is cur.body:
                return 'function', '<lambda>'
            if isinstance(cur, cst.FunctionDef):
                if child is cur.body:
                    return 'function', cur.name.value
                return 'module', None  # 裝飾器 / 參數預設值
            child, cur = cur, parents.get(cur)
        return 'module', None

    def enclosing_stmt(node, parents):
        cur = node
        while cur is not None:
            if isinstance(cur, (cst.SimpleStatementLine, cst.BaseCompoundStatement)):
                return cur
            cur = parents.get(cur)
        return node

    code_dir = out_dir / 'code'
    code_dir.mkdir(parents=True, exist_ok=True)
    mutants = []
    for rel in targets:
        src = (REPO_ROOT / rel).read_text()
        wrapper = cst.MetadataWrapper(cst.parse_module(src))
        positions = wrapper.resolve(PositionProvider)
        parents = wrapper.resolve(ParentNodeProvider)
        collector = Collector()
        wrapper.visit(collector)
        seen = set()
        count = 0
        for node, mutated, op_name in collector.candidates:
            new_code = wrapper.module.deep_replace(node, mutated).code
            if new_code == src:
                continue
            try:
                compile(new_code, rel, 'exec')
            except SyntaxError:
                continue
            digest = hashlib.sha1(new_code.encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)

            pos_node = node
            while positions.get(pos_node) is None:
                pos_node = parents[pos_node]
            pos = positions[pos_node]
            scope, func = scope_of(pos_node, parents)
            if isinstance(node, cst.FunctionDef):
                scope, func = 'module', node.name.value
            if isinstance(node, (cst.If, cst.While)):
                select = [pos.start.line, positions[node.test].end.line]
            else:
                stmt_line = positions[enclosing_stmt(pos_node, parents)].start.line
                select = [min(stmt_line, pos.start.line), pos.end.line]

            count += 1
            mid = f'{rel[:-3].replace("/", ".")}#{count}'
            code_path = code_dir / f'{mid}.py'
            code_path.write_text(new_code)
            mutants.append({
                'id': mid, 'file': rel, 'line': pos.start.line, 'select_lines': select,
                'scope': scope, 'function': func, 'operator': op_name, 'code_path': str(code_path),
            })
    with open(out_dir / 'mutants.jsonl', 'w') as f:
        for mu in mutants:
            f.write(json.dumps(mu, ensure_ascii=False) + '\n')
    return mutants


# =============================================================================
# Worker 與測試執行
# =============================================================================


def make_worker(worker_dir):
    if worker_dir.exists():
        shutil.rmtree(worker_dir)
    worker_dir.mkdir(parents=True)
    with tempfile.TemporaryFile() as buf:
        with tarfile.open(fileobj=buf, mode='w') as tar:
            def keep(info):
                return None if Path(info.name).name in COPY_EXCLUDES else info
            for child in REPO_ROOT.iterdir():
                if child.name not in COPY_EXCLUDES and child.resolve() != worker_dir.parents[1].resolve():
                    tar.add(child, arcname=child.name, filter=keep)
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode='r') as tar:
            tar.extractall(worker_dir, filter='data')
    (worker_dir / 'mutation_settings.py').write_text(MUTATION_SETTINGS)


def worker_env(index, worker_dir):
    env = dict(os.environ)
    env.update({
        'POSTGRES_DB': f'mut_w{index}',
        'PYTHONDONTWRITEBYTECODE': '1',  # 變異檔與原檔可能同秒同大小，避免讀到舊的 .pyc
        'PYTHONPATH': str(worker_dir),
    })
    return env


def pytest_cmd(tests=None, extra=()):
    cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--ds=mutation_settings',
           '--no-header', *extra]
    return cmd + list(tests or [])


def run_mutant(index, worker_dir, mutant, tests, originals):
    target = worker_dir / mutant['file']
    original = originals[mutant['file']]
    if target.read_text() != original:
        raise RuntimeError(f'worker {index} 的 {mutant["file"]} 未還原')
    target.write_text(Path(mutant['code_path']).read_text())
    started = time.time()
    try:
        proc = subprocess.run(
            pytest_cmd(tests, ['-x', '--reuse-db', '-rfE', '--tb=no']),
            cwd=worker_dir, env=worker_env(index, worker_dir),
            capture_output=True, text=True, timeout=90 if tests else 300,
        )
        code, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        code, output = 'timeout', ''
    finally:
        target.write_text(original)
    if code == 'timeout':
        status = 'timeout'
    elif code == 0:
        status = 'survived'
    elif code in (1, 2):  # 測試失敗 / 收集時出錯（例如 import 就爆）都算被殺死
        status = 'killed'
    else:
        status = f'error{code}'
    return {
        'id': mutant['id'], 'status': status, 'exit': code, 'duration': round(time.time() - started, 2),
        'n_tests': len(tests) if tests else 'all',
        'killed_by': [ln for ln in output.splitlines() if ln.startswith(('FAILED ', 'ERROR '))][:3],
        'tail': output.strip().splitlines()[-15:] if status.startswith('error') else [],
    }


def load_coverage_map(cov_file, worker_root):
    from coverage import CoverageData

    data = CoverageData(basename=str(cov_file))
    data.read()
    cmap = {}
    for measured in data.measured_files():
        by_line = {}
        for line, contexts in data.contexts_by_lineno(measured).items():
            tests = {c.rsplit('|', 1)[0] for c in contexts if c}
            if tests:
                by_line[line] = tests
        cmap[os.path.relpath(measured, worker_root)] = by_line
    return cmap


def select_tests(mutant, cmap):
    """函式內變異 → 覆蓋該行的測試；模組層或找不到覆蓋測試 → None（跑全套）"""
    if mutant['scope'] != 'function':
        return None
    by_line = cmap.get(mutant['file'], {})
    start, end = mutant['select_lines']
    tests = set()
    for line in range(start, end + 1):
        tests |= by_line.get(line, set())
    return sorted(tests) or None


def run_parallel(jobs, workers, worker_root, originals, results_path, label):
    job_queue = queue.Queue()
    for job in jobs:
        job_queue.put(job)
    lock = threading.Lock()
    done = {'n': 0}
    started = time.time()

    with open(results_path, 'a') as out:
        def work(index):
            worker_dir = worker_root / f'w{index}'
            while True:
                try:
                    mutant, tests = job_queue.get_nowait()
                except queue.Empty:
                    return
                result = run_mutant(index, worker_dir, mutant, tests, originals)
                with lock:
                    out.write(json.dumps(result, ensure_ascii=False) + '\n')
                    out.flush()
                    done['n'] += 1
                    if done['n'] % 100 == 0 or done['n'] == len(jobs):
                        print(f'[{label}] {done["n"]}/{len(jobs)}（{time.time() - started:.0f}s）', flush=True)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(1, workers + 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()


def drop_test_databases(workers):
    import psycopg

    conninfo = {
        'host': os.environ.get('POSTGRES_HOST', 'django-postgres'),
        'port': int(os.environ.get('POSTGRES_PORT', '5432')),
        'user': os.environ.get('POSTGRES_USER', 'myuser'),
        'password': os.environ.get('POSTGRES_PASSWORD', 'password123'),
        'dbname': 'postgres',
    }
    with psycopg.connect(**conninfo, autocommit=True) as conn:
        for i in range(workers + 1):
            conn.execute(f'DROP DATABASE IF EXISTS test_mut_w{i}')


def cmd_run(args):
    out_dir = Path(args.out or tempfile.mkdtemp(prefix='mutation-')).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    worker_root = out_dir / 'workers'
    print(f'輸出目錄：{out_dir}', flush=True)

    targets = args.files or TARGETS
    mutants = generate_mutants(out_dir, targets)
    print(f'產生 {len(mutants)} 個變異體', flush=True)

    for i in range(args.workers + 1):
        make_worker(worker_root / f'w{i}')

    # 基準：每個 worker 建好自己的測試庫並確認全綠；w0 同時收集「每行被哪些測試執行」
    def baseline(i):
        extra = ['--create-db']
        if i == 0:
            extra += ['--cov=shortener', '--cov=ninja_shortener', '--cov-context=test', '--cov-report=']
        wd = worker_root / f'w{i}'
        return subprocess.run(pytest_cmd(extra=extra), cwd=wd, env=worker_env(i, wd),
                              capture_output=True, text=True)

    procs = {}
    threads = [threading.Thread(target=lambda i=i: procs.__setitem__(i, baseline(i)))
               for i in range(args.workers + 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    failed = {i: p for i, p in procs.items() if p.returncode != 0}
    if failed:
        i, p = next(iter(failed.items()))
        sys.exit(f'基準測試未全綠（worker {i}），請先修正：\n{p.stdout[-3000:]}{p.stderr[-2000:]}')
    print('基準測試全綠', flush=True)

    cmap = load_coverage_map(worker_root / 'w0' / '.coverage', worker_root / 'w0')
    originals = {f: (REPO_ROOT / f).read_text() for f in targets}
    jobs = [(mu, select_tests(mu, cmap)) for mu in mutants]
    jobs.sort(key=lambda job: job[1] is not None)  # 全套（較慢）的先跑，避免尾端卡單一長任務
    results_path = out_dir / 'results.jsonl'
    results_path.unlink(missing_ok=True)
    run_parallel(jobs, args.workers, worker_root, originals, results_path, '變異')

    # 複驗：只跑部分測試就存活的，改跑全套確認
    results = [json.loads(ln) for ln in open(results_path)]
    by_id = {mu['id']: mu for mu in mutants}
    recheck = [(by_id[r['id']], None) for r in results if r['status'] == 'survived' and r['n_tests'] != 'all']
    verify_path = out_dir / 'verify.jsonl'
    verify_path.unlink(missing_ok=True)
    if recheck:
        run_parallel(recheck, args.workers, worker_root, originals, verify_path, '複驗')

    if not args.keep:
        shutil.rmtree(worker_root)
        drop_test_databases(args.workers)
    cmd_report(argparse.Namespace(out=str(out_dir), diffs=False))


# =============================================================================
# 報告
# =============================================================================


def cmd_report(args):
    out_dir = Path(args.out)
    mutants = {json.loads(ln)['id']: json.loads(ln) for ln in open(out_dir / 'mutants.jsonl')}
    results = {}
    for name in ('results.jsonl', 'verify.jsonl'):
        path = out_dir / name
        if path.exists():
            for ln in open(path):
                r = json.loads(ln)
                results[r['id']] = r

    def score(counter):
        killed = counter['killed'] + counter['timeout']
        total = killed + counter['survived']
        return killed, total, (100 * killed / total if total else 100.0)

    overall, per_file, per_op = Counter(), defaultdict(Counter), defaultdict(Counter)
    errors = []
    for mid, r in results.items():
        if r['status'].startswith('error'):
            errors.append(r)
            continue
        mu = mutants[mid]
        for counter in (overall, per_file[mu['file']], per_op[mu['operator']]):
            counter[r['status']] += 1

    killed, total, pct = score(overall)
    lines = [
        '# 變異測試結果', '',
        f'- 變異體：{total}（殺死 {killed}，其中逾時 {overall["timeout"]}；存活 {overall["survived"]}）',
        f'- **變異分數：{pct:.1f}%**',
    ]
    if errors:
        lines.append(f'- 執行異常：{len(errors)}（見 results.jsonl 的 tail 欄位）')
    lines += ['', '| 檔案 | 變異體 | 殺死 | 存活 | 分數 |', '|---|---:|---:|---:|---:|']
    for f in sorted(per_file, key=lambda f: score(per_file[f])[2]):
        k, t, s = score(per_file[f])
        lines.append(f'| {f} | {t} | {k} | {per_file[f]["survived"]} | {s:.1f}% |')
    lines += ['', '| 運算子 | 變異體 | 殺死 | 存活 | 分數 |', '|---|---:|---:|---:|---:|']
    for op in sorted(per_op, key=lambda o: -sum(per_op[o].values())):
        k, t, s = score(per_op[op])
        lines.append(f'| {op} | {t} | {k} | {per_op[op]["survived"]} | {s:.1f}% |')

    lines += ['', '## 存活的變異體', '']
    survivors = sorted(
        (mutants[mid] for mid, r in results.items() if r['status'] == 'survived'),
        key=lambda mu: (mu['file'], mu['line']),
    )
    for mu in survivors:
        original = (REPO_ROOT / mu['file']).read_text().splitlines()
        mutated = Path(mu['code_path']).read_text().splitlines()
        diff = [ln for ln in difflib.unified_diff(original, mutated, lineterm='', n=0)][2:]
        where = f'{mu["function"]}()' if mu['function'] else '模組 / 類別層'
        lines += [f'### `{mu["id"]}` L{mu["line"]} {where} [{mu["operator"]}]', '', '```diff', *diff[:10], '```', '']
    report = '\n'.join(lines) + '\n'
    (out_dir / 'report.md').write_text(report)
    print('\n'.join(lines[:4 + len(per_file) + 4]))
    print(f'\n完整報告：{out_dir / "report.md"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='產生並執行全部變異體')
    run.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    run.add_argument('--out', help='輸出目錄（預設為新的暫存目錄）')
    run.add_argument('--files', nargs='*', help=f'只變異這些檔案（預設：{len(TARGETS)} 個應用程式檔案）')
    run.add_argument('--keep', action='store_true', help='保留 worker 副本與測試資料庫（除錯用）')
    run.set_defaults(func=cmd_run)
    report = sub.add_parser('report', help='由既有結果重新產生 report.md')
    report.add_argument('--out', required=True)
    report.set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
