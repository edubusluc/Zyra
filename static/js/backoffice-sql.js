/*
 * Autocompletado de la consola SQL del back-office.
 *
 * Mientras se escribe, propone:
 *   - tablas después de FROM o JOIN;
 *   - columnas de las tablas del FROM (SELECT id, | ...);
 *   - columnas de la tabla relacionada al escribir un punto tras una clave ajena
 *     (local_id. → campos de team_team), con varios saltos (local_id.club_id.).
 *
 * `suggest` es una función pura (texto, posición del cursor, esquema) para poder
 * probarla sin navegador; `attach` monta la lista bajo el textarea.
 */
(function (root) {
    'use strict';

    var MAX_ITEMS = 50;
    // Catálogo de traducciones de Django (jsi18n); fuera del navegador (pruebas), el texto tal cual.
    var gettext = typeof root.gettext === 'function' ? root.gettext : function (s) { return s; };
    var interpolate = typeof root.interpolate === 'function' ? root.interpolate : function (fmt, obj) {
        return fmt.replace(/%\((\w+)\)s/g, function (m, k) { return String(obj[k]); });
    };
    var KEYWORDS = /^(select|from|join|left|right|inner|outer|cross|full|natural|on|where|group|order|by|having|limit|offset|union|all|distinct|as|and|or|not|in|is|null|like|between|case|when|then|else|end|with|asc|desc|using|window)$/i;

    // "FROM a x, " → después de la coma va otra tabla.
    var TABLE_LIST_COMMA = /\bfrom\s+[A-Za-z_]\w*(?:\s+(?:as\s+)?[A-Za-z_]\w*)?(?:\s*,\s*[A-Za-z_]\w*(?:\s+(?:as\s+)?[A-Za-z_]\w*)?)*\s*,\s*$/i;

    function indexSchema(schema) {
        var tables = {};
        schema.forEach(function (t) { tables[t.name.toLowerCase()] = t; });
        return tables;
    }

    // Quita cadenas y comentarios para que no cuenten al buscar FROM, alias, etc.
    function stripLiterals(text) {
        return text
            .replace(/'(?:[^']|'')*'?/g, function (m) { return ' '.repeat(m.length); })
            .replace(/--[^\n]*/g, function (m) { return ' '.repeat(m.length); });
    }

    // Tablas del FROM/JOIN con su alias: {alias → tabla}, en orden de aparición.
    function sources(text, tables) {
        var found = [];
        var re = /\b(?:from|join)\s+([A-Za-z_]\w*)(?:\s+(?:as\s+)?([A-Za-z_]\w*))?/gi;
        var m;
        while ((m = re.exec(text))) {
            var table = m[1].toLowerCase();
            if (!tables[table]) continue;
            var alias = m[2] && !KEYWORDS.test(m[2]) ? m[2].toLowerCase() : null;
            found.push({ table: table, alias: alias });
        }
        // "FROM a, b" también cuenta.
        var comma = /\bfrom\s+[A-Za-z_]\w*(?:\s+(?:as\s+)?[A-Za-z_]\w*)?((?:\s*,\s*[A-Za-z_]\w*(?:\s+(?:as\s+)?[A-Za-z_]\w*)?)+)/gi;
        while ((m = comma.exec(text))) {
            m[1].split(',').slice(1).forEach(function (part) {
                var bits = part.trim().split(/\s+/).filter(function (b) { return !/^as$/i.test(b); });
                var table = (bits[0] || '').toLowerCase();
                if (tables[table]) found.push({ table: table, alias: bits[1] && !KEYWORDS.test(bits[1]) ? bits[1].toLowerCase() : null });
            });
        }
        return found;
    }

    function findColumn(table, name) {
        name = name.toLowerCase();
        var cols = table.columns;
        for (var i = 0; i < cols.length; i++) {
            var c = cols[i].name.toLowerCase();
            if (c === name || (cols[i].target && c === name + '_id')) return cols[i];
        }
        return null;
    }

    // Recorre "local_id.club_id" hasta la tabla final, o null si algún tramo no existe.
    function walk(parts, srcs, tables) {
        var first = parts[0].toLowerCase();
        var current = null;
        var rest = parts.slice(1);
        srcs.forEach(function (s) {
            if (!current && (s.alias === first || (!s.alias && s.table === first) || s.table === first)) current = tables[s.table];
        });
        if (!current) {
            rest = parts;
            // Sin alias: el primer tramo es una clave ajena de alguna tabla del FROM.
            for (var i = 0; i < srcs.length && !current; i++) {
                if (findColumn(tables[srcs[i].table], first)) current = tables[srcs[i].table];
            }
        }
        if (!current) return null;
        for (var j = 0; j < rest.length; j++) {
            var col = findColumn(current, rest[j]);
            if (!col || !col.target || !tables[col.target.toLowerCase()]) return null;
            current = tables[col.target.toLowerCase()];
        }
        return current;
    }

    function columnItems(table, prefix, label) {
        return table.columns
            .filter(function (c) { return c.name.toLowerCase().indexOf(prefix) === 0; })
            .map(function (c) { return { value: c.name, target: c.target || '', table: label || table.name }; });
    }

    /*
     * Devuelve {items, start, end, title} o null. `start`/`end` delimitan el trozo que
     * se sustituye al elegir una sugerencia.
     */
    function suggest(text, caret, schema) {
        var tables = indexSchema(schema);
        var clean = stripLiterals(text);
        var before = clean.slice(0, caret);
        // Dentro de una cadena o de un comentario no se propone nada.
        var raw = text.slice(0, caret);
        if ((raw.split("'").length - 1) % 2 === 1 || /--[^\n]*$/.test(raw.replace(/'(?:[^']|'')*'/g, "''"))) return null;

        var tokenMatch = /([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\.?|)$/.exec(before);
        var token = tokenMatch[1];
        var tokenStart = caret - token.length;
        var after = /^\w*/.exec(clean.slice(caret))[0];
        var end = caret + after.length;
        var head = before.slice(0, tokenStart);
        var srcs = sources(clean, tables);

        if (token.indexOf('.') >= 0) {
            var parts = token.split('.');
            var partial = parts.pop().toLowerCase();
            var table = walk(parts, srcs, tables);
            if (!table) return null;
            return finish(columnItems(table, partial), caret - partial.length, end, partial,
                          interpolate(gettext('Campos de %(table)s (%(path)s)'), { table: table.name, path: parts.join('.') }, true));
        }

        var prefix = token.toLowerCase();
        if (/\b(?:from|join)\s+$/i.test(head) || TABLE_LIST_COMMA.test(head)) {
            var names = schema.filter(function (t) { return t.name.toLowerCase().indexOf(prefix) === 0; })
                .map(function (t) { return { value: t.name, target: '', table: '' }; });
            return finish(names, tokenStart, end, prefix, gettext('Tablas'));
        }
        // Justo tras "FROM tabla " va el alias: no hay nada que proponer.
        if (/\b(?:from|join)\s+[A-Za-z_]\w*\s+(?:as\s+)?$/i.test(head)) return null;
        if (KEYWORDS.test(token)) return null;
        // Sin nada escrito, solo se abre tras una coma, un paréntesis o una palabra clave.
        if (!token && !/(?:,|\(|\b(?:select|distinct|where|and|or|on|by|having|not)\s)\s*$/i.test(head)) return null;
        if (!srcs.length) return null;

        var items = [];
        var seen = {};
        srcs.forEach(function (s) {
            var key = s.alias || s.table;
            if (seen[key]) return;
            seen[key] = true;
            items = items.concat(columnItems(tables[s.table], prefix, key));
        });
        var title = srcs.length === 1 ? interpolate(gettext('Campos de %(table)s'), { table: srcs[0].table }, true) : gettext('Campos');
        var result = finish(items, tokenStart, end, prefix, title);
        // Con varias tablas, cada campo lleva al lado la tabla (o el alias) de la que viene.
        if (result) result.showTable = srcs.length > 1;
        return result;
    }

    function finish(items, start, end, prefix, title) {
        // Si lo escrito ya es exactamente la única opción, no molesta con la lista.
        if (!items.length || (items.length === 1 && items[0].value.toLowerCase() === prefix)) return null;
        return { items: items.slice(0, MAX_ITEMS), more: Math.max(0, items.length - MAX_ITEMS), start: start, end: end, title: title };
    }

    // ---------- Interfaz ----------

    function attach(input, schema) {
        var box = document.createElement('div');
        box.className = 'bo-ac is-hidden';
        box.setAttribute('role', 'listbox');
        box.id = input.id + '-suggestions';
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-controls', box.id);
        input.insertAdjacentElement('afterend', box);

        var state = null;
        var active = 0;

        function close() {
            state = null;
            box.classList.add('is-hidden');
            input.removeAttribute('aria-activedescendant');
        }

        function render() {
            box.innerHTML = '';
            var head = document.createElement('div');
            head.className = 'bo-ac-head';
            head.textContent = state.title;
            var hint = document.createElement('span');
            hint.textContent = gettext('↑↓ elegir · Tab o Enter insertar · Esc cerrar');
            head.appendChild(hint);
            box.appendChild(head);
            var list = document.createElement('ul');
            state.items.forEach(function (item, i) {
                var li = document.createElement('li');
                li.id = box.id + '-' + i;
                li.setAttribute('role', 'option');
                li.className = i === active ? 'is-active' : '';
                li.setAttribute('aria-selected', i === active ? 'true' : 'false');
                var name = document.createElement('span');
                name.className = 'bo-ac-name';
                name.textContent = item.value;
                li.appendChild(name);
                if (item.target) {
                    var fk = document.createElement('span');
                    fk.className = 'bo-fk';
                    fk.textContent = '→ ' + item.target;
                    li.appendChild(fk);
                } else if (item.table && state.showTable) {
                    var t = document.createElement('span');
                    t.className = 'bo-ac-table';
                    t.textContent = item.table;
                    li.appendChild(t);
                }
                li.addEventListener('mousedown', function (e) {
                    e.preventDefault();  // que el textarea no pierda el foco
                });
                li.addEventListener('click', function () { choose(i); });
                list.appendChild(li);
            });
            if (state.more) {
                var more = document.createElement('li');
                more.className = 'bo-ac-more';
                more.textContent = interpolate(gettext('y %(n)s más: sigue escribiendo para filtrar'), { n: state.more }, true);
                list.appendChild(more);
            }
            box.appendChild(list);
            box.classList.remove('is-hidden');
            input.setAttribute('aria-activedescendant', box.id + '-' + active);
            var current = list.children[active];
            if (current && current.scrollIntoView) current.scrollIntoView({ block: 'nearest' });
        }

        function refresh() {
            state = suggest(input.value, input.selectionStart, schema);
            active = 0;
            if (state) render(); else close();
        }

        function choose(i) {
            var item = state.items[i];
            var value = input.value;
            input.value = value.slice(0, state.start) + item.value + value.slice(state.end);
            var pos = state.start + item.value.length;
            input.focus();
            input.selectionStart = input.selectionEnd = pos;
            close();
        }

        input.addEventListener('input', refresh);
        input.addEventListener('click', close);
        input.addEventListener('blur', close);
        input.addEventListener('keydown', function (e) {
            if (e.ctrlKey && e.key === ' ') { e.preventDefault(); refresh(); return; }
            if (!state) return;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                var n = state.items.length;
                active = (active + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
                render();
            } else if ((e.key === 'Enter' || e.key === 'Tab') && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
                e.preventDefault();
                choose(active);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                close();
            }
        });
    }

    var api = { suggest: suggest, attach: attach };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.ZyraSql = api;
})(this);
