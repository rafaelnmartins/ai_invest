#!/usr/bin/env python3
"""Stockgaide /research/ — monthly rebuild.

Input : the JSON from GET https://stockgaide.rafaelnm.workers.dev/research-export
        (worker v2.131+: the dashboard's own sizing, line by line) and the
        currently published research/index.html (its <style> block and SVG
        defs are reused; its month table is used to guarantee that months
        already published did not change).
Output: index.html (EN + PT) and memoria_calculo_research_{mmm}{yyyy}.xlsx,
        both covering every CLOSED month up to --ate (default: calc.json's
        throughMonth). Numbers come straight from calc.json, so they match the
        dashboard by construction.

usage: build_research.py export.json template_index.html outdir [--ate YYYY-MM] [--hoje YYYY-MM-DD]
exit 2 = data does not match the dashboard; exit 3 = a month already published would change (nothing written).
"""
import argparse, calendar, datetime as dt, json, re, sys
from collections import defaultdict

MES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESL_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MESL_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
NUM_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
NUM_PT = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze"]
PERFIL_EN = {"MACDLE Premium": "MACDLE Premium", "MACD": "MACD", "MACDLE CTRL Regular": "MACDLE CTRL Regular",
             "CP v11 MEDIUM Melhor": "CP v11 MEDIUM (better)", "CP v11 MEDIUM Normal": "CP v11 MEDIUM (normal)",
             "CP v11 STRONG Premium": "CP v11 STRONG Premium", "Cauteloso / PF ausente": "Cautious / no PF", "Evitar": "Avoid"}
CRITERIO = {"MACDLE Premium": "MACDLE, ① CORE, Prob ≥70%, PF ≥1,51", "MACD": "MACDLE, CORE/CTRL, Prob ≥60%, PF 1,40–1,70",
            "MACDLE CTRL Regular": "MACDLE, ② CTRL, Prob 60–69%, PF 1,40–1,60", "CP v11 MEDIUM Melhor": "CP v11, ◆ MEDIUM, Score 55–64, PF ≥1,30",
            "CP v11 MEDIUM Normal": "CP v11, ◆ MEDIUM, Score ≥65, PF ≥1,30", "CP v11 STRONG Premium": "CP v11, ⬆ STRONG, Score ≥85, PF ≥2,00",
            "Cauteloso / PF ausente": "PF ausente, prob baixa ou sinal incompleto", "Evitar": "Regras mandam não operar"}
CLASSE = {"": "—", "CLASSE_1_CORE": "① CORE", "CLASSE_2_CONTROLADO": "② CTRL", "SCORE_OK": "✓ OK", "SCORE_FORTE": "⬆ STRONG",
          "SCORE_MEDIO": "◆ MEDIUM", "PF_BAIXO_PROB_OK": "PF baixo"}


# ── number formatting (PT numbers are generated here, never by regex over HTML) ──
def _grp(n, sep):
    s = f"{int(round(abs(n))):d}"
    out = ""
    for i, ch in enumerate(reversed(s)):
        if i and i % 3 == 0:
            out = sep + out
        out = ch + out
    return out

def money(v, lang, sign=True):
    sg = ("+" if v >= 0 else "-") if sign else ("-" if v < 0 else "")
    if round(abs(v)) == 0:
        sg = "+" if sign else ""
    return f"{sg}${_grp(v, ',')}" if lang == "en" else f"{sg}US$ {_grp(v, '.')}"

def pct(v, d, lang, sign=True):
    s = f"{abs(v):.{d}f}"
    if lang == "pt":
        s = s.replace(".", ",")
    sg = ("+" if v >= 0 else "-") if sign else ("-" if v < 0 else "")
    return f"{sg}{s}%"

def num(v, d, lang):
    s = f"{v:.{d}f}"
    return s.replace(".", ",") if lang == "pt" else s


def stats(rows, base):
    rows = sorted(rows, key=lambda x: x["exitTime"])
    n = len(rows)
    wins = sum(1 for x in rows if x["pnlPct"] > 0)
    gp = sum(x["usd"] for x in rows if x["usd"] > 0)
    gl = -sum(x["usd"] for x in rows if x["usd"] < 0)
    eq = peak = float(base); dd = 0.0
    for x in rows:
        eq += x["usd"]; peak = max(peak, eq); dd = min(dd, (eq - peak) / peak * 100)
    worst = min(rows, key=lambda x: x["usd"]); best = max(rows, key=lambda x: x["usd"])
    return {"n": n, "wins": wins, "losers": n - wins, "winrate": wins / n * 100 if n else 0,
            "pf": gp / gl if gl else float("inf"), "dd": dd, "worst": worst, "best": best,
            "usd": sum(x["usd"] for x in rows)}


def build(calc, ate, hoje):
    base = calc["base"]
    rows = [x for x in calc["rows"] if x["mes"] <= ate]
    rows.sort(key=lambda x: (x["exitTime"], x["symbol"]))
    meses = sorted({x["mes"] for x in rows})
    M = []
    acum = 0.0
    for m in meses:
        rr = [x for x in rows if x["mes"] == m]
        usd = sum(x["usd"] for x in rr); p = usd / base * 100; acum += p
        M.append({"m": m, "n": len(rr), "wins": sum(1 for x in rr if x["pnlPct"] > 0), "usd": usd, "pct": p, "acum": acum})
    # conferência contra o que o dashboard calculou (calc.json months)
    ref = {mo["m"]: mo for mo in calc["months"]}
    for mo in M:
        r = ref.get(mo["m"])
        if not r or abs(r["usd"] - mo["usd"]) > 0.01 or r["n"] != mo["n"]:
            sys.exit(f"ERRO: mês {mo['m']} não bate com o dashboard ({r} vs {mo})")
    S = stats(rows, base)
    prof = defaultdict(list)
    for x in rows:
        prof[x["perfil"]].append(x)
    P = []
    for k, v in prof.items():
        P.append({"perfil": k, "size": calc["sizingFloors"].get(k, 0), "n": len(v),
                  "wins": sum(1 for x in v if x["pnlPct"] > 0), "avg": sum(x["pnlPct"] for x in v) / len(v),
                  "usd": sum(x["usd"] for x in v)})
    P.sort(key=lambda p: (p["size"] == 0, -p["usd"]))
    regimeZero = [x for x in rows if x.get("regimeZero")]
    return {"base": base, "rows": rows, "M": M, "S": S, "P": P, "ate": ate, "hoje": hoje, "regime": calc.get("regime") or {},
            "regimeZero": regimeZero}


# ─────────────────────────────── HTML ───────────────────────────────
def bar_chart(M, lang):
    n = len(M); slot = 700 / n; w = slot * 0.56
    mx = max(0, max(m["pct"] for m in M)); mn = min(0, min(m["pct"] for m in M))
    rng = (mx - mn) or 1
    y0 = 30 + 140 * mx / rng
    out = [f'<line class="ax" x1="30.0" y1="{y0:.1f}" x2="730.0" y2="{y0:.1f}"/>']
    nomes = MES_EN if lang == "en" else MES_PT
    for i, m in enumerate(M):
        h = 140 * abs(m["pct"]) / rng; x = 30 + i * slot + (slot - w) / 2; cx = x + w / 2
        lab = nomes[int(m["m"][5:]) - 1]
        val = pct(m["pct"], 1, lang)
        if m["pct"] >= 0:
            out.append(f'<rect x="{x:.1f}" y="{y0 - h:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="url(#g1)"/>'
                       f'<text x="{cx:.1f}" y="{y0 - h - 7:.1f}" class="bv">{val}</text>')
        else:
            out.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="#F0757A"/>'
                       f'<text x="{cx:.1f}" y="{y0 - 7:.1f}" class="bv" style="fill:#F0757A">{val}</text>')
        out.append(f'<text x="{cx:.1f}" y="192.0" class="bl">{lab}</text>')
    return "\n      ".join(out)


def curve(M, lang):
    pts_v = [0.0] + [m["acum"] for m in M]
    mx = max(pts_v); mn = min(pts_v); rng = (mx - mn) or 1
    xs = [38 + i * (684 / (len(pts_v) - 1)) for i in range(len(pts_v))]
    ys = [170 - 140 * (v - mn) / rng for v in pts_v]
    ybase = 170 - 140 * (0 - mn) / rng
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    poly = f"{xs[0]:.1f},{ybase:.1f} {pts} {xs[-1]:.1f},{ybase:.1f}"
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#5C5AF0"/>' for x, y in list(zip(xs, ys))[1:])
    lx = min(xs[-1] - 34, 688)
    ly = ys[-1] + 22 if len(ys) > 1 and ys[-1] > ys[-2] else max(14, ys[-1] - 8)   # caiu no último mês: rótulo abaixo do ponto
    return (f'<polygon points="{poly}" fill="url(#g2)"/>\n'
            f'      <polyline points="{pts}" fill="none" stroke="#5C5AF0" stroke-width="2.5" stroke-linejoin="round"/>\n'
            f'      {circles}\n'
            f'      <text x="{lx:.0f}" y="{ly:.0f}" class="bv" style="font-size:13px">{pct(M[-1]["acum"], 2, lang)}</text>')


def cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def month_table(M, lang, base):
    nomes = MES_EN if lang == "en" else MES_PT
    out = []
    for m in M:
        wr = m["wins"] / m["n"] * 100 if m["n"] else 0
        c = cls(m["usd"])
        out.append(f'<tr><td>{nomes[int(m["m"][5:]) - 1]}</td><td>{m["n"]}</td><td>{num(wr, 1, lang)}%</td>'
                   f'<td class="{c}">{money(m["usd"], lang)}</td><td class="{c}">{pct(m["pct"], 2, lang)}</td>'
                   f'<td class="hl">{pct(m["acum"], 2, lang)}</td></tr>')
    return "".join(out)


def prof_table(P, lang):
    out = []
    for p in P:
        nome = PERFIL_EN.get(p["perfil"], p["perfil"]) if lang == "en" else p["perfil"]
        wr = p["wins"] / p["n"] * 100
        c = cls(round(p["usd"]))
        out.append(f'<tr><td>{nome}</td><td>{num(p["size"] * 100, 1, lang)}%</td><td>{p["n"]}</td><td>{num(wr, 1, lang)}%</td>'
                   f'<td>{pct(p["avg"], 2, lang)}</td><td{(" class=" + chr(34) + c + chr(34)) if c else ""}>{money(p["usd"], lang)}</td></tr>')
    return "".join(out)


def curve_text(M, lang):
    nomes = MESL_EN if lang == "en" else MESL_PT
    neg = [m for m in M if m["pct"] < 0]
    pos = len(M) - len(neg)
    best = max(M, key=lambda m: m["usd"])
    nm = lambda m: nomes[int(m["m"][5:]) - 1]
    low_wr = [m for m in M if m["n"] and m["wins"] / m["n"] < 0.5]
    if lang == "en":
        title = "Every month closed positive" if not neg else f"{NUM_EN[pos].capitalize() if pos <= 12 else pos} of {NUM_EN[len(M)] if len(M) <= 12 else len(M)} months closed positive"
        parts = []
        if neg:
            parts.append(("Only " if len(neg) == 1 else "") + ", ".join(f"{nm(m).capitalize()} ({pct(m['pct'], 2, 'en')})" for m in neg)
                         + (" closed negative" if len(neg) > 1 else " closed negative") + " — it is in the cumulative below, not hidden.")
        weakest = min([m for m in M if m["pct"] >= 0], key=lambda m: m["pct"], default=None)
        if weakest and not neg:
            parts.append(f"{nm(weakest).capitalize()} was the weakest ({pct(weakest['pct'], 2, 'en')}).")
        parts.append(f"{nm(best).capitalize()} was the strongest in dollars ({money(best['usd'], 'en')}).")
        if low_wr:
            parts.append("Months with a win rate below 50%: " + ", ".join(nm(m).capitalize() for m in low_wr) + ".")
        parts.append("The line below is the cumulative return, not a projection — it stops where the data stops.")
    else:
        title = "Todos os meses fecharam positivos" if not neg else f"{NUM_PT[pos].capitalize() if pos <= 12 else pos} de {NUM_PT[len(M)] if len(M) <= 12 else len(M)} meses fecharam positivos"
        parts = []
        if neg:
            parts.append(("Só " if len(neg) == 1 else "") + ", ".join(f"{nm(m) if len(neg) == 1 else nm(m).capitalize()} ({pct(m['pct'], 2, 'pt')})" for m in neg)
                         + (" fechou negativo" if len(neg) == 1 else " fecharam negativos") + " — e está no acumulado abaixo, não escondido.")
        weakest = min([m for m in M if m["pct"] >= 0], key=lambda m: m["pct"], default=None)
        if weakest and not neg:
            parts.append(f"{nm(weakest).capitalize()} foi o mais fraco ({pct(weakest['pct'], 2, 'pt')}).")
        parts.append(f"{nm(best).capitalize()} foi o mais forte em dólares ({money(best['usd'], 'pt')}).")
        if low_wr:
            parts.append("Meses com acerto abaixo de 50%: " + ", ".join(nm(m) for m in low_wr) + ".")
        parts.append("A linha abaixo é o retorno acumulado, não uma projeção — ela para onde os dados param.")
    return title, " ".join(parts)


def avoid_note(P, lang):
    ev = next((p for p in P if p["size"] == 0), None)
    if not ev:
        return ""
    a = ev["avg"]
    if lang == "en":
        j = ("they averaged a loss, so skipping them was correct." if a < 0 else
             "they finished close to neutral, so skipping them cost little." if a < 1.5 else
             "they averaged a gain, so skipping them left some upside on the table — the rule trades that for consistency.")
        return (f'<p class="note">The "Avoid" tier is worth noticing: {ev["n"]} trades the rules refused to size, '
                f'averaging {pct(a, 2, "en")} each. They add $0 by design — {j}</p>')
    j = ("tiveram perda média, então evitá-las estava certo." if a < 0 else
         "ficaram perto do neutro, então evitá-las custou pouco." if a < 1.5 else
         "tiveram ganho médio, então evitá-las deixou algum ganho na mesa — a regra troca isso por consistência.")
    return (f'<p class="note">A faixa "Evitar" merece atenção: {ev["n"]} operações que as regras se recusaram a dimensionar, '
            f'com resultado médio de {pct(a, 2, "pt")}. Elas somam US$ 0 por definição — {j}</p>')


def regime_li(D, lang):
    rg = D["regime"]
    fim = D["ate"] + "-31"
    if not rg.get("ligado") or not rg.get("ativadoEm") or rg["ativadoEm"] > fim:
        return ""
    y, m, d = rg["ativadoEm"].split("-")
    nz = len(D["regimeZero"])
    if lang == "en":
        return (f'    <li><b>Market regime.</b> Since {MES_EN[int(m) - 1]} {int(d)}, {y}, entries made while the IWM (Russell 2000) '
                f'trend indicator is in a downtrend are sized at 0% — the same rule the live dashboard applies. '
                + (f'{nz} trade{"s" if nz != 1 else ""} in this period fell under it.' if nz else 'No trade in this period has fallen under it yet.') + '</li>\n')
    return (f'    <li><b>Regime de mercado.</b> Desde {int(d)}/{m}/{y}, entradas feitas com o indicador de tendência do IWM '
            f'(Russell 2000) em baixa recebem 0% — a mesma regra do painel ao vivo. '
            + (f'{nz} operaç{"ões" if nz != 1 else "ão"} do período caí{"ram" if nz != 1 else "u"} nessa regra.' if nz else 'Nenhuma operação do período caiu nessa regra ainda.') + '</li>\n')


def render_lang(D, lang, xlsx_name):
    M, S, P, base = D["M"], D["S"], D["P"], D["base"]
    last = M[-1]; y, mo = last["m"].split("-"); mo = int(mo)
    total = sum(m["usd"] for m in M); totp = total / base * 100
    nmes = len(M)
    first_exit = min(x["exitTime"] for x in D["rows"])[:10]
    fy, fm, fd = first_exit.split("-")
    nxt = MESL_EN[mo % 12] if lang == "en" else MESL_PT[mo % 12]
    ultimo_dia = calendar.monthrange(int(y), mo)[1]
    worst, best = S["worst"], S["best"]
    if lang == "en":
        eyebrow = f'Stockgaide Research · <b>Study Nº 01</b> · {MES_EN[mo - 1]} {y}'
        h1 = "What $100,000 following our signals would have done."
        dek = (f"Every trade our engine opens and closes is logged automatically. We took all {S['n']} closed trades from January to "
               f"{MESL_EN[mo - 1]} {y}, sized each one by its conviction profile, and added up the result — winners, losers and everything between.")
        head = (f'<span class="from">$100,000</span>\n    <span class="arrow">→</span>\n    <span class="big">${_grp(base + total, ",")}</span>\n'
                f'    <div class="headnote">A gross {"gain" if total >= 0 else "loss"} of <b>{pct(totp, 2, "en")}</b> from {MESL_EN[int(fm) - 1]} {int(fd)} to {MESL_EN[mo - 1]} {ultimo_dia}, '
                f'with a maximum drawdown of {pct(S["dd"], 2, "en")}. {S["losers"]} of the {S["n"]} trades lost money and are counted in that number.</div>')
        stat_k = ["Closed trades", "Win rate", "Profit factor", "Max drawdown"]
        bar_h3 = f"Monthly return on the $100,000 base"
        bar_aria = f"Monthly returns, January to {MESL_EN[mo - 1]} {y}"
        kick1, kick2, kick3, kick4 = "The curve", "Method", "Where it came from", "Limitations"
        ctitle, ctext = curve_text(M, "en")
        cap1 = "Month by month — $100,000 base"
        th1 = "<th>Month</th><th>Trades</th><th>Win rate</th><th>Result</th><th>Return</th><th>Cumulative</th>"
        small = (f"January starts on the {int(fd)}{'th' if 11 <= int(fd) <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(int(fd) % 10, 'th')} "
                 f"and {MESL_EN[mo - 1]} ends on the {ultimo_dia}{'st' if ultimo_dia == 31 else 'th'} — the first month is partial. "
                 f"{nxt} is still open and is excluded, exactly as the dashboard does.")
        meth = (f'    <li><b>Real trades, logged automatically.</b> Each entry and exit was recorded by the system as it happened, with price and timestamp. Nothing was selected afterwards: all {S["n"]} closed trades are in.</li>\n'
                '    <li><b>Position size follows conviction.</b> Each trade gets the share of capital its profile prescribes — from 14% for the highest-conviction long-term setups down to 3.5% for incomplete signals, and 0% for the ones the rules say to skip. We used the <b>floor</b> of every band, never the top.</li>\n'
                '    <li><b>Capital rotates.</b> Each trade uses its nominal percentage of the $100,000 base independently of how many other positions were open at the time.</li>\n'
                f'    <li><b>Losses count the same as gains.</b> A trade that lost {num(abs(worst["pnlPct"]), 1, "en")}% subtracts exactly what its size prescribes. The worst single trade cost {money(worst["usd"], "en", False).lstrip("-")}; the best added {money(best["usd"], "en", False)}.</li>\n'
                + regime_li(D, "en") +
                '    <li><b>Gross, not net.</b> No brokerage fees, no slippage, no taxes. Exits use the price recorded when the exit signal fired.</li>')
        dl_b, dl_t, dl_btn = ("Check the math yourself",
                              f"The full workbook: all {S['n']} trades line by line, with entry, exit, conviction profile, size and contribution. Formulas are live — change the base capital and everything recalculates.",
                              "Download the spreadsheet (XLSX)")
        h2_3 = "Contribution by conviction profile"
        p3 = "The framework sizes each signal by how much the system trusts it. This is what each tier actually delivered — including the tier that is deliberately sized at zero."
        cap3 = "By profile — sizing floor applied"
        th3 = "<th>Profile</th><th>Size</th><th>Trades</th><th>Win rate</th><th>Avg result</th><th>Contribution</th>"
        lim = ('  <h2 class="t">What this is <em>not</em></h2>\n'
               '  <p><b>Not net of costs.</b> Fees, slippage and taxes would reduce it. How much depends on the broker and the account.</p>\n'
               f'  <p><b>One regime.</b> January to {MESL_EN[mo - 1]} {y}, including a historic rotation out of mega-cap technology. A different market would give a different number.</p>\n'
               '  <p><b>Past is not future.</b> This is a measurement of what happened, published for transparency — not a promise of what will happen.</p>')
        cta = ('<div class="cta">\n  <h3>This engine is licensable</h3>\n  <p>The signals above are generated automatically after every U.S. market close, with an auditable log running since January 2026. If your platform needs a signal feed or per-ticker AI analysis — white-label, PT/EN — let\'s talk.</p>\n'
               '  <a class="btn" href="mailto:stockgaide@gmail.com?subject=Signal%20feed%20licensing">Contact for licensing</a>\n</div>')
        stat_v = [str(S["n"]), f"{num(S['winrate'], 1, 'en')}%", num(S["pf"], 2, "en"), pct(S["dd"], 2, "en")]
    else:
        eyebrow = f'Stockgaide Research · <b>Estudo Nº 01</b> · {MES_PT[mo - 1]} {y}'
        h1 = "O que US$ 100.000 seguindo nossos sinais teriam feito."
        dek = (f"Toda operação que o nosso motor abre e fecha é registrada automaticamente. Pegamos as {S['n']} operações fechadas de janeiro a "
               f"{MESL_PT[mo - 1]} de {y}, dimensionamos cada uma pelo seu perfil de convicção e somamos o resultado — ganhos, perdas e tudo no meio.")
        head = (f'<span class="from">US$ 100.000</span>\n    <span class="arrow">→</span>\n    <span class="big">US$ {_grp(base + total, ".")}</span>\n'
                f'    <div class="headnote">{"Ganho" if total >= 0 else "Perda"} brut{"o" if total >= 0 else "a"} de <b>{pct(totp, 2, "pt")}</b> de {int(fd)} de {MESL_PT[int(fm) - 1]} a {ultimo_dia} de {MESL_PT[mo - 1]}, '
                f'com drawdown máximo de {pct(S["dd"], 2, "pt")}. {S["losers"]} das {S["n"]} operações deram prejuízo e estão contadas nesse número.</div>')
        stat_k = ["Operações", "Taxa de acerto", "Profit factor", "Drawdown máx."]
        bar_h3 = "Retorno mensal sobre a base de US$ 100.000"
        bar_aria = f"Retornos mensais, janeiro a {MESL_PT[mo - 1]} de {y}"
        kick1, kick2, kick3, kick4 = "A curva", "Método", "De onde veio", "Limitações"
        ctitle, ctext = curve_text(M, "pt")
        cap1 = "Mês a mês — base US$ 100.000"
        th1 = "<th>Mês</th><th>Operações</th><th>Acerto</th><th>Resultado</th><th>Retorno</th><th>Acumulado</th>"
        small = (f"Janeiro começa no dia {int(fd)} e {MESL_PT[mo - 1]} termina no dia {ultimo_dia} — o primeiro mês é parcial. "
                 f"{nxt.capitalize()} ainda está aberto e fica de fora, exatamente como no painel.")
        meth = (f'    <li><b>Operações reais, registradas automaticamente.</b> Cada entrada e saída foi gravada pelo sistema no momento em que aconteceu, com preço e horário. Nada foi selecionado depois: as {S["n"]} operações fechadas estão todas aqui.</li>\n'
                '    <li><b>O tamanho segue a convicção.</b> Cada operação recebe a fatia de capital que seu perfil determina — de 14% para os sinais de longo prazo com maior convicção até 3,5% para sinais incompletos, e 0% para os que as regras mandam evitar. Usamos o <b>piso</b> de cada faixa, nunca o teto.</li>\n'
                '    <li><b>O capital gira.</b> Cada operação usa seu percentual nominal sobre a base de US$ 100.000, independentemente de quantas outras posições estavam abertas ao mesmo tempo.</li>\n'
                f'    <li><b>Perdas contam igual aos ganhos.</b> Uma operação que perdeu {num(abs(worst["pnlPct"]), 1, "pt")}% subtrai exatamente o que seu tamanho determina. A pior sozinha custou {money(worst["usd"], "pt", False).lstrip("-")}; a melhor somou {money(best["usd"], "pt", False)}.</li>\n'
                + regime_li(D, "pt") +
                '    <li><b>Bruto, não líquido.</b> Sem corretagem, sem slippage, sem impostos. As saídas usam o preço registrado quando o sinal de saída disparou.</li>')
        dl_b, dl_t, dl_btn = ("Confira a conta você mesmo",
                              f"A memória de cálculo completa: as {S['n']} operações linha a linha, com entrada, saída, perfil de convicção, tamanho e contribuição. As fórmulas estão vivas — troque o capital base e tudo recalcula.",
                              "Baixar a planilha (XLSX)")
        h2_3 = "Contribuição por perfil de convicção"
        p3 = "O modelo dimensiona cada sinal pelo quanto o sistema confia nele. Isto é o que cada faixa entregou de fato — incluindo a que é deliberadamente dimensionada em zero."
        cap3 = "Por perfil — piso do sizing aplicado"
        th3 = "<th>Perfil</th><th>Tamanho</th><th>Operações</th><th>Acerto</th><th>Resultado médio</th><th>Contribuição</th>"
        lim = ('  <h2 class="t">O que isto <em>não</em> é</h2>\n'
               '  <p><b>Não é líquido de custos.</b> Corretagem, slippage e impostos reduziriam o número. Quanto depende da corretora e da conta.</p>\n'
               f'  <p><b>Um regime só.</b> Janeiro a {MESL_PT[mo - 1]} de {y}, incluindo uma rotação histórica para fora das mega-caps de tecnologia. Um mercado diferente daria um número diferente.</p>\n'
               '  <p><b>Passado não é futuro.</b> Isto é uma medição do que aconteceu, publicada por transparência — não uma promessa do que vai acontecer.</p>')
        cta = ('<div class="cta">\n  <h3>Este motor é licenciável</h3>\n  <p>Os sinais acima são gerados automaticamente após cada fechamento do mercado americano, com log auditável rodando desde janeiro de 2026. Se a sua plataforma precisa de um feed de sinais ou de análise de IA por ticker — white-label, PT/EN — vamos conversar.</p>\n'
               '  <a class="btn" href="mailto:stockgaide@gmail.com?subject=Licenciamento%20do%20feed%20de%20sinais">Contato para licenciamento</a>\n</div>')
        stat_v = [str(S["n"]), f"{num(S['winrate'], 1, 'pt')}%", num(S["pf"], 2, "pt"), pct(S["dd"], 2, "pt")]
    stats_html = "\n".join(f'    <div class="stat"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in zip(stat_k, stat_v))
    return f'''<div class="hero">
  <div class="eyebrow">{eyebrow}</div>
  <h1>{h1}</h1>
  <p class="dek">{dek}</p>
</div>

<div class="ledger">
  <div class="head">
    {head}
  </div>
  <div class="chartbox">
    <h3>{bar_h3}</h3>
    <svg viewBox="0 0 760 210" role="img" aria-label="{bar_aria}">
      {bar_chart(M, lang)}
    </svg>
  </div>
  <div class="stats">
{stats_html}
  </div>
</div>

<section>
  <div class="kicker">{kick1}</div>
  <h2 class="t">{ctitle}</h2>
  <p>{ctext}</p>
  <div class="chartbox" style="border:1px solid var(--line);border-radius:14px;background:var(--card);margin:16px 0 6px">
    <h3>{"Cumulative return" if lang == "en" else "Retorno acumulado"}</h3>
    <svg viewBox="0 0 760 200" role="img" aria-label="{"Cumulative return curve" if lang == "en" else "Curva de retorno acumulado"}">
      {curve(M, lang)}
    </svg>
  </div>

  <div class="tblwrap"><table>
    <caption>{cap1}</caption>
    <thead><tr>{th1}</tr></thead>
    <tbody>{month_table(M, lang, base)}</tbody>
  </table></div>
  <p class="small">{small}</p>
</section>

<section>
  <div class="kicker">{kick2}</div>
  <h2 class="t">{"How the number was built" if lang == "en" else "Como o número foi construído"}</h2>
  <ol class="method">
{meth}
  </ol>

  <div class="dlbox">
    <div class="dltxt">
      <b>{dl_b}</b>
      <span class="small">{dl_t}</span>
    </div>
    <a class="dlbtn" href="/research/{xlsx_name}" download>{dl_btn}</a>
  </div>
</section>

<section>
  <div class="kicker">{kick3}</div>
  <h2 class="t">{h2_3}</h2>
  <p>{p3}</p>
  <div class="tblwrap"><table>
    <caption>{cap3}</caption>
    <thead><tr>{th3}</tr></thead>
    <tbody>{prof_table(P, lang)}</tbody>
  </table></div>
  {avoid_note(P, lang)}
</section>

<section>
  <div class="kicker">{kick4}</div>
{lim}
</section>

{cta}'''


def render_html(D, template, xlsx_name):
    style = re.search(r"<style>.*?</style>", template, re.S).group(0)
    if "td.neg{" not in style:                     # meses/perfis negativos em vermelho
        style = style.replace("</style>", "td.neg{color:var(--red)}\n</style>")
    defs = re.search(r'<svg width="0" height="0"[^\n]*</svg>', template).group(0)
    M, S = D["M"], D["S"]
    last = M[-1]; y, mo = last["m"].split("-"); mo = int(mo)
    total = sum(m["usd"] for m in M); totp = total / D["base"] * 100
    first_exit = min(x["exitTime"] for x in D["rows"])[:10]
    ultimo = f'{y}-{mo:02d}-{calendar.monthrange(int(y), mo)[1]:02d}'
    hoje = D["hoje"]; hy, hm, hd = hoje.split("-")
    desc_en = (f"{S['n']} closed trades, January to {MESL_EN[mo - 1]} {y}, position-sized exactly like our live dashboard. "
               "Monthly and cumulative returns on a $100,000 portfolio — losses included.")
    desc_pt = (f"{S['n']} operações fechadas, de janeiro a {MESL_PT[mo - 1]} de {y}, dimensionadas exatamente como no nosso painel ao vivo. "
               "Retorno mensal e acumulado sobre US$ 100.000 — perdas incluídas.")
    og = (f"{S['n']} closed trades, Jan–{MES_EN[mo - 1]} {y}, sized exactly like our live dashboard: {pct(totp, 2, 'en')} "
          f"with a {pct(S['dd'], 2, 'en')} maximum drawdown. Full method, every loss included.")
    worst = S["worst"]
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Article", "@id": "https://stockgaide.com/research/#article", "headline": "What $100,000 Following Our Signals Would Have Done",
         "description": f"Position-sizing simulation over {S['n']} real closed trades from January to {MESL_EN[mo - 1]} {y}: monthly returns, cumulative curve, drawdown and profit factor on a $100,000 portfolio.",
         "datePublished": "2026-08-03", "dateModified": hoje, "inLanguage": ["en", "pt-BR"],
         "author": {"@type": "Organization", "name": "Stockgaide", "url": "https://stockgaide.com"},
         "publisher": {"@type": "Organization", "name": "Stockgaide", "url": "https://stockgaide.com", "logo": {"@type": "ImageObject", "url": "https://stockgaide.com/icons/icon-512.png"}},
         "mainEntityOfPage": "https://stockgaide.com/research/"},
        {"@type": "Dataset", "@id": "https://stockgaide.com/research/#dataset", "name": f"Stockgaide closed-trade log (Jan–{MES_EN[mo - 1]} {y})",
         "description": f"{S['n']} automatically logged closed trades with entry price, exit price, realized percentage result, strategy, conviction class, probability and profit factor. Every trade the engine opened is included, winners and losers alike.",
         "temporalCoverage": f"{first_exit}/{ultimo}", "dateModified": hoje,
         "creator": {"@type": "Organization", "name": "Stockgaide", "url": "https://stockgaide.com"},
         "variableMeasured": ["monthly return", "cumulative return", "win rate", "profit factor", "maximum drawdown", "contribution by conviction profile"],
         "measurementTechnique": "Each closed trade's realized percentage is weighted by the position size its conviction profile prescribes, applied to a $100,000 base. Capital is assumed to rotate: each trade uses its nominal percentage independently."},
        {"@type": "FAQPage", "@id": "https://stockgaide.com/research/#faq", "mainEntity": [
            {"@type": "Question", "name": "Is this a live-traded account?", "acceptedAnswer": {"@type": "Answer", "text": "No. The trades are real and were logged automatically as they happened. This is not a brokerage statement."}},
            {"@type": "Question", "name": "Are losing trades included?", "acceptedAnswer": {"@type": "Answer", "text": f"Yes. All {S['n']} closed trades are included — {S['losers']} of them lost money. Nothing was filtered out, and the worst single contribution was {money(worst['usd'], 'en')}."}},
            {"@type": "Question", "name": "Does the simulation account for fees and slippage?", "acceptedAnswer": {"@type": "Answer", "text": "No. Results are gross: no brokerage fees, no slippage, no taxes. Exits use the price recorded when the exit signal fired."}}]}]}
    xlsx_name = xlsx_name
    upd_en = f"Data through {MES_EN[mo - 1]} {calendar.monthrange(int(y), mo)[1]}, {y} · Updated {MES_EN[int(hm) - 1]} {int(hd)}, {hy}."
    upd_pt = f"Dados até {calendar.monthrange(int(y), mo)[1]:02d}/{mo:02d}/{y} · Atualizado em {hd}/{hm}/{hy}."
    title_en = "What $100,000 Following Our Signals Would Have Done — Stockgaide Research"
    title_pt = "O Que US$ 100.000 Seguindo Nossos Sinais Teriam Feito — Stockgaide Research"
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_en}</title>
<meta name="description" content="{desc_en}">
<link rel="canonical" href="https://stockgaide.com/research/">
<meta name="robots" content="index,follow">
<meta property="og:title" content="What $100,000 Following Our Signals Would Have Done">
<meta property="og:description" content="{og}">
<meta property="og:url" content="https://stockgaide.com/research/">
<meta property="og:type" content="article">
<meta property="og:image" content="https://stockgaide.com/icons/icon-512.png">
<link rel="icon" href="/icons/icon-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..700;1,9..40,400&family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False)}
</script>
{style}
</head>
<body>
{defs}
<div class="wrap">

<div class="top">
  <div class="brand">stock g<span class="ai">AI</span>de <span style="font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.14em">RESEARCH</span></div>
  <div class="langs" role="group" aria-label="Language">
    <button id="btn-en" class="on" onclick="setLang('en')">EN</button>
    <button id="btn-pt" onclick="setLang('pt')">PT</button>
  </div>
</div>

<!-- ═══════════ ENGLISH ═══════════ -->
<div class="lang-en">

{render_lang(D, "en", xlsx_name)}
</div>

<!-- ═══════════ PORTUGUÊS ═══════════ -->
<div class="lang-pt">

{render_lang(D, "pt", xlsx_name)}
</div>

<footer>
  <div class="links">
    <a href="/">Home</a><a href="/stocks">Stocks A–Z</a><a href="/blog">Blog</a><a href="mailto:stockgaide@gmail.com">stockgaide@gmail.com</a>
  </div>
  <div class="lang-en">Educational platform. Analyses are used by the creator in his own decisions. Not investment advice. {upd_en}</div>
  <div class="lang-pt">Plataforma educacional. Análises usadas pelo criador nas próprias decisões. Não é recomendação de investimento. {upd_pt}</div>
</footer>
</div>

<script>
(function(){{
  var T={{en:{{title:{json.dumps(title_en, ensure_ascii=False)},
             desc:{json.dumps(desc_en, ensure_ascii=False)}}},
          pt:{{title:{json.dumps(title_pt, ensure_ascii=False)},
             desc:{json.dumps(desc_pt, ensure_ascii=False)}}}}};
  window.setLang=function(l){{
    document.documentElement.setAttribute("lang", l==="pt"?"pt-BR":"en");
    document.getElementById("btn-en").classList.toggle("on",l==="en");
    document.getElementById("btn-pt").classList.toggle("on",l==="pt");
    document.title=T[l].title;
    var m=document.querySelector('meta[name="description"]'); if(m)m.setAttribute("content",T[l].desc);
    try{{localStorage.setItem("sg_lang",l);}}catch(e){{}}
  }};
  var saved=null; try{{saved=localStorage.getItem("sg_lang");}}catch(e){{}}
  var q=new URLSearchParams(location.search).get("lang");
  var nav=(navigator.language||"").toLowerCase().indexOf("pt")===0?"pt":"en";
  setLang(q==="pt"||q==="en"?q:(saved==="pt"||saved==="en"?saved:nav));
}})();
</script>
</body>
</html>
'''


# ─────────────────────────────── XLSX ───────────────────────────────
def build_xlsx(D, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment
    A = "Arial"
    HF = Font(name=A, size=10, bold=True, color="FFFFFF"); HFILL = PatternFill("solid", fgColor="0A1428")
    F = Font(name=A, size=10); FB = Font(name=A, size=11, bold=True); BLUE = Font(name=A, size=11, color="0000FF")
    GREY = Font(name=A, size=9, color="666666"); NOTE = Font(name=A, size=9)
    USD = '\\$#,##0;"($"#,##0\\);\\-'; PCT2 = '0.00%;\\(0.00%\\);\\-'
    rows, M, base = D["rows"], D["M"], D["base"]
    last = M[-1]; y, mo = last["m"].split("-"); mo = int(mo)
    n = len(rows); L = n + 1           # last data row
    first_exit = min(x["exitTime"] for x in rows)[:10]
    fy, fm, fd = first_exit.split("-")
    ultimo = calendar.monthrange(int(y), mo)[1]
    wb = Workbook()

    # Premissas
    ws = wb.active; ws.title = "Premissas"
    ws["A1"] = "Memória de cálculo — retorno de US$ 100.000 seguindo as recomendações"; ws["A1"].font = Font(name=A, size=14, bold=True)
    ws["A2"] = f"Reproduz o cálculo do dashboard · período {fd}/{fm}/{fy} a {ultimo:02d}/{mo:02d}/{y} · {n} operações"; ws["A2"].font = Font(name=A, size=10, color="666666")
    ws["A4"] = "Capital base (US$)"; ws["A4"].font = FB
    ws["B4"] = base; ws["B4"].font = BLUE; ws["B4"].fill = PatternFill("solid", fgColor="FFFF00"); ws["B4"].number_format = "\\$#,##0"
    ws["C4"] = "← edite aqui: toda a planilha recalcula"; ws["C4"].font = GREY
    ws["A6"] = "Regra de dimensionamento (piso de cada faixa, definido pelo Rafa)"; ws["A6"].font = FB
    for c, t in zip("ABC", ["Perfil", "Critério", "Sizing"]):
        ws[f"{c}7"] = t; ws[f"{c}7"].font = HF; ws[f"{c}7"].fill = HFILL
    perfis = ["MACDLE Premium", "MACD", "MACDLE CTRL Regular", "CP v11 MEDIUM Melhor", "CP v11 MEDIUM Normal",
              "CP v11 STRONG Premium", "Cauteloso / PF ausente", "Evitar"]
    for i, p in enumerate(perfis):
        r = 8 + i
        ws[f"A{r}"] = p; ws[f"A{r}"].font = Font(name=A, size=11)
        ws[f"B{r}"] = CRITERIO[p]; ws[f"B{r}"].font = Font(name=A, size=11)
        ws[f"C{r}"] = D_floor(D, p); ws[f"C{r}"].font = BLUE; ws[f"C{r}"].number_format = "0.0%"
    rg = D["regime"]
    notas = [
        ("Regras aplicadas (as mesmas do dashboard público)", FB),
        ("1. O perfil de cada operação vem da função classifyTradeProfile do worker — a mesma que o dashboard usa.", NOTE),
        ("2. O capital gira: cada operação usa seu % nominal sobre a base, independentemente de quantas estavam abertas.", NOTE),
        ("3. Resultado BRUTO: sem corretagem, sem slippage, sem impostos.", NOTE),
        ((f"4. Regime IWM: desde {rg['ativadoEm'][8:10]}/{rg['ativadoEm'][5:7]}/{rg['ativadoEm'][:4]}, entradas feitas com o IWM em baixa recebem sizing 0 "
          "(coluna 'Regime IWM' = sim na aba Operações)." if rg.get("ativadoEm") else "4. Regime IWM: não estava ativo no período."), NOTE),
        ("5. As operações são reais e foram registradas automaticamente; o dimensionamento é aplicado retroativamente. NÃO é extrato de corretora.", NOTE),
        (f"6. O mês corrente fica fora do acumulado, como no dashboard. Primeiro mês parcial (começa em {fd}/{fm}).", NOTE),
    ]
    for i, (t, f) in enumerate(notas):
        r = 17 + i; ws[f"A{r}"] = t; ws[f"A{r}"].font = f
    ws.column_dimensions["A"].width = 26; ws.column_dimensions["B"].width = 46; ws.column_dimensions["C"].width = 12

    # Operações
    wo = wb.create_sheet("Operações")
    hdr = ["#", "Símbolo", "Estratégia", "Classe", "Score", "Prob %", "PF", "Entrada", "Saída", "Dias", "P/L %",
           "Perfil de convicção", "Sizing %", "Alocação US$", "Contribuição US$", "Acumulado US$", "Regime IWM"]
    for j, h in enumerate(hdr, 1):
        c = wo.cell(1, j, h); c.font = HF; c.fill = HFILL; c.alignment = Alignment(horizontal="center")
    for i, x in enumerate(rows):
        r = i + 2
        ent = dt.date.fromisoformat(x["entryTime"][:10]) if x.get("entryTime") else None
        sai = dt.date.fromisoformat(x["exitTime"][:10])        # DATA SEM HORA: senão o SUMIFS do mês perde a operação
        prob = x["prob"]
        vals = [i + 1, x["symbol"], x["strategy"] or "sem etiqueta", CLASSE.get(x["classe"], x["classe"] or "—"),
                x["score"], (prob / 100 if prob is not None else None), x["pf"], ent, sai,
                ((sai - ent).days if ent else None), x["pnlPct"] / 100, x["perfil"],
                f'=IF(Q{r}="sim",0,IFERROR(INDEX(Premissas!$C$8:$C$15,MATCH(L{r},Premissas!$A$8:$A$15,0)),0))',
                f"=Premissas!$B$4*M{r}", f"=N{r}*K{r}", (f"=O{r}" if r == 2 else f"=P{r - 1}+O{r}"),
                "sim" if x.get("regimeZero") else "não"]
        fmts = [None, None, None, None, "0.0", "0.0%", "0.000", "dd/mm/yyyy", "dd/mm/yyyy", "0", PCT2, None, "0.0%", USD, USD, USD, None]
        for j, (v, f) in enumerate(zip(vals, fmts), 1):
            c = wo.cell(r, j, v); c.font = F
            if f: c.number_format = f
    for col, wdt in zip("ABCDEFGHIJKLMNOPQ", [5, 10, 13, 12, 7, 8, 7, 11, 11, 7, 9, 22, 10, 14, 16, 15, 11]):
        wo.column_dimensions[col].width = wdt
    wo.freeze_panes = "A2"
    wo["Q1"].comment = Comment("sim = entrada feita com o IWM em baixa depois da ativação da regra: sizing 0, como no dashboard.", "Stockgaide")

    # Mês a mês
    wm = wb.create_sheet("Mês a mês")
    wm["A1"] = "Resultado mensal — calculado por SUMIFS sobre a aba Operações"; wm["A1"].font = Font(name=A, size=12, bold=True)
    for j, h in enumerate(["Mês", "Início", "Fim", "Operações", "Ganhadoras", "Acerto %", "Resultado US$", "Retorno %", "Acumulado %"], 1):
        c = wm.cell(3, j, h); c.font = HF; c.fill = HFILL
    I = f"Operações!$I$2:$I${L}"; K = f"Operações!$K$2:$K${L}"; O = f"Operações!$O$2:$O${L}"
    for i, m in enumerate(M):
        r = 4 + i; yy, mm = int(m["m"][:4]), int(m["m"][5:])
        wm[f"A{r}"] = f"{MES_PT[mm - 1]}/{yy}"
        wm[f"B{r}"] = dt.date(yy, mm, 1); wm[f"C{r}"] = dt.date(yy, mm, calendar.monthrange(yy, mm)[1])
        wm[f"D{r}"] = f'=COUNTIFS({I},">="&$B{r},{I},"<="&$C{r})'
        wm[f"E{r}"] = f'=COUNTIFS({I},">="&$B{r},{I},"<="&$C{r},{K},">0")'
        wm[f"F{r}"] = f"=IFERROR(E{r}/D{r},0)"
        wm[f"G{r}"] = f'=SUMIFS({O},{I},">="&$B{r},{I},"<="&$C{r})'
        wm[f"H{r}"] = f"=G{r}/Premissas!$B$4"
        wm[f"I{r}"] = f"=H{r}" if i == 0 else f"=I{r - 1}+H{r}"
        for c, f in zip("ABCDEFGHI", [None, "dd/mm/yyyy", "dd/mm/yyyy", "0", "0", "0.0%", USD, PCT2, PCT2]):
            wm[f"{c}{r}"].font = F
            if f: wm[f"{c}{r}"].number_format = f
    t = 4 + len(M)
    wm[f"A{t}"] = "TOTAL"; wm[f"D{t}"] = f"=SUM(D4:D{t - 1})"; wm[f"E{t}"] = f"=SUM(E4:E{t - 1})"
    wm[f"F{t}"] = f"=IFERROR(E{t}/D{t},0)"; wm[f"G{t}"] = f"=SUM(G4:G{t - 1})"; wm[f"H{t}"] = f"=G{t}/Premissas!$B$4"
    for c, f in zip("ADEFGH", [None, "0", "0", "0.0%", USD, PCT2]):
        wm[f"{c}{t}"].font = Font(name=A, size=11, bold=True)
        if f: wm[f"{c}{t}"].number_format = f
    nxt = MESL_PT[mo % 12]
    wm[f"A{t + 2}"] = f"Nota: janeiro começa em {fd}/{fm}. {nxt.capitalize()} (mês corrente) não entra, como no dashboard."; wm[f"A{t + 2}"].font = NOTE
    for col, wdt in zip("ABCDEFGHI", [12, 11, 11, 11, 12, 10, 15, 11, 12]):
        wm.column_dimensions[col].width = wdt

    # Por perfil
    wp = wb.create_sheet("Por perfil")
    wp["A1"] = "Contribuição por perfil de convicção — SUMIFS sobre a aba Operações"; wp["A1"].font = Font(name=A, size=12, bold=True)
    for j, h in enumerate(["Perfil", "Sizing %", "Operações", "Ganhadoras", "Acerto %", "P/L médio %", "Contribuição US$", "% do total"], 1):
        c = wp.cell(3, j, h); c.font = HF; c.fill = HFILL
    Lr = f"Operações!$L$2:$L${L}"
    tp = 4 + len(D["P"])
    for i, p in enumerate(D["P"]):
        r = 4 + i
        wp[f"A{r}"] = p["perfil"]
        wp[f"B{r}"] = f"=IFERROR(INDEX(Premissas!$C$8:$C$15,MATCH($A{r},Premissas!$A$8:$A$15,0)),0)"
        wp[f"C{r}"] = f"=COUNTIF({Lr},$A{r})"
        wp[f"D{r}"] = f'=COUNTIFS({Lr},$A{r},{K},">0")'
        wp[f"E{r}"] = f"=IFERROR(D{r}/C{r},0)"
        wp[f"F{r}"] = f"=IFERROR(SUMIF({Lr},$A{r},{K})/C{r},0)"
        wp[f"G{r}"] = f"=SUMIF({Lr},$A{r},{O})"
        wp[f"H{r}"] = f"=IFERROR(G{r}/$G${tp},0)"
        for c, f in zip("ABCDEFGH", [None, "0.0%", "0", "0", "0.0%", PCT2, USD, "0.0%"]):
            wp[f"{c}{r}"].font = Font(name=A, size=11, bold=(c == "A"))
            if f: wp[f"{c}{r}"].number_format = f
    wp[f"A{tp}"] = "TOTAL"; wp[f"C{tp}"] = f"=SUM(C4:C{tp - 1})"; wp[f"G{tp}"] = f"=SUM(G4:G{tp - 1})"
    for c, f in zip("ACG", [None, "0", USD]):
        wp[f"{c}{tp}"].font = Font(name=A, size=11, bold=True)
        if f: wp[f"{c}{tp}"].number_format = f
    wp[f"A{tp + 2}"] = "Observação: operações com Regime IWM = sim aparecem no perfil delas, mas contribuem US$ 0 (sizing 0)."; wp[f"A{tp + 2}"].font = NOTE
    for col, wdt in zip("ABCDEFGH", [24, 10, 11, 12, 10, 12, 16, 11]):
        wp.column_dimensions[col].width = wdt

    # Sensibilidade
    wsn = wb.create_sheet("Sensibilidade")
    sem = sum(1 for x in rows if not x["strategy"])
    wsn["A1"] = "Teste de robustez — e se as operações sem etiqueta fossem todas dimensionadas no mínimo?"; wsn["A1"].font = Font(name=A, size=12, bold=True)
    wsn["A3"] = (f"{sem} das {n} operações são anteriores à etiqueta de estratégia; nelas o perfil foi inferido por probabilidade e profit factor. "
                 "Se essa inferência estivesse inflando o resultado, forçar TODAS ao menor tamanho não-zero (3,5%) derrubaria o número."); wsn["A3"].font = F
    for j, h in enumerate(["Cenário", "Descrição", "Resultado US$", "Retorno %"], 1):
        c = wsn.cell(7, j, h); c.font = HF; c.fill = HFILL
    C = f"Operações!$C$2:$C${L}"
    wsn["A8"] = "Base"; wsn["B8"] = "Perfil inferido por prob/PF nas operações sem etiqueta"
    wsn["C8"] = f"=SUM({O})"; wsn["D8"] = "=C8/Premissas!$B$4"
    wsn["A9"] = "Conservador"; wsn["B9"] = "Sem etiqueta forçadas a 3,5% (menor sizing não-zero)"
    wsn["C9"] = f'=SUMIF({C},"<>sem etiqueta",{O})+SUMIF({C},"sem etiqueta",{K})*Premissas!$B$4*0.035'; wsn["D9"] = "=C9/Premissas!$B$4"
    for r in (8, 9):
        for c, f in zip("ABCD", [None, None, USD, PCT2]):
            wsn[f"{c}{r}"].font = F
            if f: wsn[f"{c}{r}"].number_format = f
    wsn.column_dimensions["A"].width = 14; wsn.column_dimensions["B"].width = 52; wsn.column_dimensions["C"].width = 15; wsn.column_dimensions["D"].width = 11
    wb.save(path)


def D_floor(D, perfil):
    return D["calc_floors"].get(perfil, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("calc"); ap.add_argument("template"); ap.add_argument("outdir")
    ap.add_argument("--ate"); ap.add_argument("--hoje", default=dt.date.today().isoformat())
    a = ap.parse_args()
    calc = json.load(open(a.calc))
    ate = a.ate or calc["throughMonth"]
    if ate > calc["throughMonth"]:
        sys.exit(f"ERRO: {ate} ainda não fechou no dashboard (fechado até {calc['throughMonth']})")
    D = build(calc, ate, a.hoje)
    D["calc_floors"] = calc["sizingFloors"]
    y, mo = ate.split("-")
    xlsx_name = f"memoria_calculo_research_{MES_PT[int(mo) - 1].lower()}{y}.xlsx"
    template = open(a.template, encoding="utf-8").read()
    if calc.get("confere") is False:
        sys.exit(2)
    # O passado não muda: meses já publicados precisam sair idênticos (n e US$).
    publicados = {}
    m_en = re.search(r'<div class="lang-en">.*?<tbody>(.*?)</tbody>', template, re.S)
    if m_en:
        for nome, n_, usd in re.findall(r'<tr><td>(\w{3})</td><td>(\d+)</td><td>[^<]*</td><td[^>]*>([+-]\$[\d,]+)</td>', m_en.group(1)):
            publicados[nome] = (int(n_), int(usd.replace("$", "").replace(",", "")))
    mudou = []
    for mo in D["M"]:
        nome = MES_EN[int(mo["m"][5:]) - 1]
        if nome in publicados and mo["m"] < ate:
            n_pub, usd_pub = publicados[nome]
            if n_pub != mo["n"] or abs(usd_pub - round(mo["usd"])) > 1:
                mudou.append(f'{mo["m"]}: publicado {n_pub} ops / {usd_pub} US$, agora {mo["n"]} ops / {round(mo["usd"])} US$')
    if mudou:
        print(json.dumps({"erro": "mês já publicado mudaria", "detalhes": mudou}, ensure_ascii=False))
        sys.exit(3)
    html = render_html(D, template, xlsx_name)
    open(f"{a.outdir}/index.html", "w", encoding="utf-8").write(html)
    build_xlsx(D, f"{a.outdir}/{xlsx_name}")
    S = D["S"]; tot = sum(m["usd"] for m in D["M"])
    print(json.dumps({"ate": ate, "trades": S["n"], "acumuladoPct": round(tot / D["base"] * 100, 4), "acumuladoUsd": round(tot, 2),
                      "meses": [(m["m"], round(m["pct"], 2), m["n"]) for m in D["M"]], "winrate": round(S["winrate"], 1),
                      "pf": round(S["pf"], 2), "dd": round(S["dd"], 2), "xlsx": xlsx_name}, ensure_ascii=False))


if __name__ == "__main__":
    main()
