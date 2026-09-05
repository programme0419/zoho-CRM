/* REFCALC reference engine.
 * Single-line signed-32-bit integer expression evaluator with house semantics.
 * Reads one expression per line from stdin, prints one result per line:
 * a decimal 32-bit integer, or "ERR".
 *
 * This source is used only to build the reference binary; it is not shipped.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <ctype.h>

typedef struct {
    const char *s;
    size_t i;
    size_t n;
    int err;
} P;

static void skip_ws(P *p) {
    while (p->i < p->n && (p->s[p->i] == ' ' || p->s[p->i] == '\t')) p->i++;
}

/* peek next significant char, 0 if end */
static char peek(P *p) {
    skip_ws(p);
    return p->i < p->n ? p->s[p->i] : 0;
}

static uint32_t wadd(uint32_t a, uint32_t b) { return a + b; }
static uint32_t wsub(uint32_t a, uint32_t b) { return a - b; }
static uint32_t wmul(uint32_t a, uint32_t b) { return a * b; }

/* C-style truncated division/modulo with INT_MIN/-1 defined to wrap. */
static int32_t idiv(int32_t a, int32_t b, int *err) {
    if (b == 0) { *err = 1; return 0; }
    if (a == INT32_MIN && b == -1) return INT32_MIN;
    return a / b;
}
static int32_t imod(int32_t a, int32_t b, int *err) {
    if (b == 0) { *err = 1; return 0; }
    if (a == INT32_MIN && b == -1) return 0;
    return a % b;
}

/* power with house rules; result is 32-bit wrapped. */
static int32_t ipow(int32_t base, int32_t exp, int *err) {
    if (exp < 0) {
        if (base == 0) { *err = 1; return 0; }
        if (base == 1) return 1;
        if (base == -1) return (exp % 2 == 0) ? 1 : -1;
        return 0;
    }
    uint32_t result = 1u;
    uint32_t b = (uint32_t)base;
    uint32_t e = (uint32_t)exp;
    while (e > 0) {
        if (e & 1u) result = wmul(result, b);
        b = wmul(b, b);
        e >>= 1;
    }
    return (int32_t)result;
}

static int32_t parse_expr(P *p);

/* atom := number | '(' expr ')' */
static int32_t parse_atom(P *p) {
    char c = peek(p);
    if (c == '(') {
        p->i++;
        int32_t v = parse_expr(p);
        if (peek(p) != ')') { p->err = 1; return 0; }
        p->i++;
        return v;
    }
    if (c == '0' && p->i + 1 < p->n && (p->s[p->i+1] == 'x' || p->s[p->i+1] == 'X')) {
        p->i += 2;
        if (p->i >= p->n || !isxdigit((unsigned char)p->s[p->i])) { p->err = 1; return 0; }
        uint32_t v = 0;
        while (p->i < p->n && isxdigit((unsigned char)p->s[p->i])) {
            char d = p->s[p->i++];
            uint32_t dv = (d <= '9') ? (uint32_t)(d - '0')
                        : (uint32_t)(tolower((unsigned char)d) - 'a' + 10);
            v = wadd(wmul(v, 16u), dv);
        }
        return (int32_t)v;
    }
    if (isdigit((unsigned char)c)) {
        uint32_t v = 0;
        while (p->i < p->n && isdigit((unsigned char)p->s[p->i])) {
            uint32_t dv = (uint32_t)(p->s[p->i++] - '0');
            v = wadd(wmul(v, 10u), dv);
        }
        return (int32_t)v;
    }
    p->err = 1;
    return 0;
}

/* unary := ('+'|'-') unary | atom   (binds tighter than '^') */
static int32_t parse_unary(P *p) {
    char c = peek(p);
    if (c == '-') { p->i++; return (int32_t)wsub(0u, (uint32_t)parse_unary(p)); }
    if (c == '+') { p->i++; return parse_unary(p); }
    return parse_atom(p);
}

/* pow := unary ('^' unary)*   (LEFT associative) */
static int32_t parse_pow(P *p) {
    int32_t v = parse_unary(p);
    while (peek(p) == '^') {
        p->i++;
        int32_t rhs = parse_unary(p);
        v = ipow(v, rhs, &p->err);
    }
    return v;
}

/* mul := pow (('*'|'/'|'%') pow)* */
static int32_t parse_mul(P *p) {
    int32_t v = parse_pow(p);
    for (;;) {
        char c = peek(p);
        if (c == '*') { p->i++; v = (int32_t)wmul((uint32_t)v, (uint32_t)parse_pow(p)); }
        else if (c == '/') { p->i++; v = idiv(v, parse_pow(p), &p->err); }
        else if (c == '%') { p->i++; v = imod(v, parse_pow(p), &p->err); }
        else break;
    }
    return v;
}

/* add := mul (('+'|'-') mul)* */
static int32_t parse_add(P *p) {
    int32_t v = parse_mul(p);
    for (;;) {
        char c = peek(p);
        if (c == '+') { p->i++; v = (int32_t)wadd((uint32_t)v, (uint32_t)parse_mul(p)); }
        else if (c == '-') { p->i++; v = (int32_t)wsub((uint32_t)v, (uint32_t)parse_mul(p)); }
        else break;
    }
    return v;
}

static int32_t parse_expr(P *p) { return parse_add(p); }

static void eval_line(const char *line) {
    size_t n = strlen(line);
    P p = { line, 0, n, 0 };
    /* empty (only whitespace) -> ERR */
    if (peek(&p) == 0) { printf("ERR\n"); return; }
    int32_t v = parse_expr(&p);
    if (p.err || peek(&p) != 0) { printf("ERR\n"); return; }
    printf("%d\n", v);
}

int main(void) {
    char buf[4096];
    while (fgets(buf, sizeof(buf), stdin)) {
        size_t len = strlen(buf);
        while (len > 0 && (buf[len-1] == '\n' || buf[len-1] == '\r')) buf[--len] = 0;
        eval_line(buf);
    }
    return 0;
}
