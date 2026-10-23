/* thinkNXG Docs — public site behaviour (no dependencies) */
(function () {
	"use strict";
	var cfg = window.TNXG_DOCS || {};
	var $ = function (s, r) { return (r || document).querySelector(s); };
	var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
	var isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

	function toast(msg) {
		var t = $("[data-dx-toast]");
		if (!t) return;
		t.textContent = msg;
		t.hidden = false;
		clearTimeout(toast._t);
		toast._t = setTimeout(function () { t.hidden = true; }, 2200);
	}

	function copyText(text) {
		if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
		return new Promise(function (resolve, reject) {
			var ta = document.createElement("textarea");
			ta.value = text;
			ta.style.position = "fixed";
			ta.style.opacity = "0";
			document.body.appendChild(ta);
			ta.select();
			try { document.execCommand("copy") ? resolve() : reject(); } catch (e) { reject(e); }
			document.body.removeChild(ta);
		});
	}

	/* ------------------------------------------------------------ theme */
	var themeBtn = $("[data-dx-theme]");
	if (themeBtn) {
		themeBtn.addEventListener("click", function () {
			var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
			document.documentElement.setAttribute("data-theme", next);
			try { localStorage.setItem("tnxg-docs-theme", next); } catch (e) {}
		});
	}

	/* ------------------------------------------------- sidebar + drawer */
	$$(".dx-nav-toggle").forEach(function (btn) {
		btn.addEventListener("click", function () {
			var li = btn.parentElement;
			var open = li.classList.toggle("is-open");
			btn.setAttribute("aria-expanded", open ? "true" : "false");
		});
	});
	var active = $(".dx-nav-link.is-active");
	var sidebar = $("#dx-sidebar");
	if (active && sidebar) {
		var top = active.offsetTop - sidebar.clientHeight / 3;
		if (top > 0) sidebar.scrollTop = top;
	}

	var menuBtn = $("[data-dx-menu]");
	var backdrop = $("[data-dx-close]");
	function setDrawer(open) {
		document.body.classList.toggle("dx-nav-open", open);
		if (menuBtn) menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
		if (backdrop) backdrop.hidden = !open;
	}
	if (menuBtn) menuBtn.addEventListener("click", function () {
		setDrawer(!document.body.classList.contains("dx-nav-open"));
	});
	if (backdrop) backdrop.addEventListener("click", function () { setDrawer(false); });

	/* ------------------------------------------------------- popovers */
	function popover(root, btnSel, popSel) {
		if (!root) return;
		var btn = $(btnSel, root), pop = $(popSel, root);
		function close() { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); }
		btn.addEventListener("click", function (e) {
			e.stopPropagation();
			var willOpen = pop.hidden;
			$$(".dx-switcher-menu, .dx-menu-pop").forEach(function (p) { p.hidden = true; });
			pop.hidden = !willOpen;
			btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
		});
		document.addEventListener("click", function (e) { if (!root.contains(e.target)) close(); });
		document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
		return close;
	}
	popover($("[data-dx-switcher]"), ".dx-switcher-btn", ".dx-switcher-menu");
	var closePageMenu = popover($("[data-dx-pagemenu]"), "button", ".dx-menu-pop");

	/* ------------------------------------------------- page menu items */
	var copyMd = $("[data-dx-copy-md]");
	if (copyMd && cfg.mdUrl) {
		copyMd.addEventListener("click", function () {
			fetch(cfg.mdUrl, { credentials: "same-origin" })
				.then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
				.then(copyText)
				.then(function () { toast("Page copied as Markdown"); })
				.catch(function () { toast("Couldn't copy the page. Use View as Markdown instead."); });
			if (closePageMenu) closePageMenu();
		});
	}
	var printBtn = $("[data-dx-print]");
	if (printBtn) printBtn.addEventListener("click", function () {
		if (closePageMenu) closePageMenu();
		window.print();
	});

	/* ------------------------------------------------------ code blocks */
	var pres = $$(".dx-prose pre");
	pres.forEach(function (pre) {
		var b = document.createElement("button");
		b.type = "button";
		b.className = "dx-copy-code";
		b.textContent = "Copy";
		b.addEventListener("click", function () {
			var code = pre.querySelector("code") || pre;
			copyText(code.innerText).then(function () {
				b.textContent = "Copied";
				setTimeout(function () { b.textContent = "Copy"; }, 1400);
			});
		});
		pre.appendChild(b);
	});
	if (pres.length) {
		var s = document.createElement("script");
		s.src = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js";
		s.async = true;
		s.onload = function () {
			$$(".dx-prose pre code").forEach(function (el) {
				try { window.hljs.highlightElement(el); } catch (e) {}
			});
		};
		document.head.appendChild(s);
	}

	/* ----------------------------------------- outline: current + progress */
	var tocLinks = $$("[data-dx-toc]");
	var fill = $("[data-dx-progress]");
	var article = $(".dx-prose");
	if (tocLinks.length) {
		var heads = tocLinks.map(function (a) { return document.getElementById(a.getAttribute("data-dx-toc")); });
		var ticking = false;
		var update = function () {
			ticking = false;
			var offset = parseInt(getComputedStyle(document.documentElement).scrollPaddingTop, 10) || 80;
			var cur = 0;
			for (var i = 0; i < heads.length; i++) {
				if (heads[i] && heads[i].getBoundingClientRect().top - offset <= 4) cur = i;
			}
			tocLinks.forEach(function (a, i) { a.classList.toggle("is-current", i === cur); });
			if (fill && article) {
				var r = article.getBoundingClientRect();
				var total = r.height - window.innerHeight + offset;
				var p = total > 0 ? Math.min(1, Math.max(0, (offset - r.top) / total)) : 1;
				fill.style.height = (p * 100).toFixed(2) + "%";
			}
		};
		window.addEventListener("scroll", function () {
			if (!ticking) { ticking = true; requestAnimationFrame(update); }
		}, { passive: true });
		update();
	}

	/* --------------------------------------------------------- feedback */
	var fb = $("[data-dx-feedback]");
	if (fb && cfg.page) {
		var choice = null;
		var form = $(".dx-feedback-form", fb);
		var send = function (comment) {
			var body = new URLSearchParams({ page: cfg.page, helpful: choice, comment: comment || "" });
			var headers = { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" };
			if (cfg.csrfToken) headers["X-Frappe-CSRF-Token"] = cfg.csrfToken;
			return fetch("/api/method/thinknxg_docs.api.submit_feedback", {
				method: "POST", headers: headers, body: body, credentials: "same-origin",
			}).then(function (r) {
				if (!r.ok) throw new Error(r.status);
				$(".dx-feedback-btns", fb).hidden = true;
				$(".dx-feedback-q", fb).hidden = true;
				form.hidden = true;
				$(".dx-feedback-done", fb).hidden = false;
			}).catch(function () { toast("Feedback wasn't sent. Try again in a minute."); });
		};
		$$("[data-helpful]", fb).forEach(function (b) {
			b.addEventListener("click", function () {
				choice = b.getAttribute("data-helpful");
				$$("[data-helpful]", fb).forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
				form.hidden = false;
				$("textarea", form).focus();
			});
		});
		form.addEventListener("submit", function (e) {
			e.preventDefault();
			send($("textarea", form).value);
		});
	}

	/* ----------------------------------------------------------- search */
	var modal = $("[data-dx-search]");
	if (!modal) return;
	var input = $("[data-dx-search-input]", modal);
	var list = $("[data-dx-search-results]", modal);
	var hint = $("[data-dx-search-hint]", modal);
	var allBox = $("[data-dx-search-all]", modal);
	var kbd = $("[data-dx-kbd]");
	if (kbd && isMac) kbd.textContent = "⌘ K";
	var sel = -1, timer = null, lastQ = "", seq = 0, lastFocus = null;

	function openSearch() {
		lastFocus = document.activeElement;
		modal.hidden = false;
		document.body.style.overflow = "hidden";
		input.focus();
		input.select();
	}
	function closeSearch() {
		modal.hidden = true;
		document.body.style.overflow = "";
		if (lastFocus && lastFocus.focus) lastFocus.focus();
	}
	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}
	function select(i) {
		var items = $$("li", list);
		if (!items.length) return;
		sel = (i + items.length) % items.length;
		items.forEach(function (li, k) {
			li.classList.toggle("is-sel", k === sel);
			li.setAttribute("aria-selected", k === sel ? "true" : "false");
		});
		items[sel].scrollIntoView({ block: "nearest" });
	}
	function render(rows, q) {
		sel = -1;
		if (!rows.length) {
			list.innerHTML = "";
			hint.textContent = "No pages match “" + q + "”. Try a shorter word or the name of a form, such as Sales Invoice.";
			hint.hidden = false;
			return;
		}
		hint.hidden = true;
		var showSpace = allBox && allBox.checked;
		list.innerHTML = rows.map(function (r) {
			var path = [showSpace ? r.space : null, r.breadcrumb].filter(Boolean).join(" › ");
			return '<li role="option"><a href="' + esc(r.url) + '">' +
				'<span class="dx-sr-title">' + esc(r.title) + "</span>" +
				(path ? '<span class="dx-sr-path">' + esc(path) + "</span>" : "") +
				(r.snippet ? '<span class="dx-sr-snip">' + r.snippet + "</span>" : "") +
				"</a></li>";
		}).join("");
		select(0);
	}
	function run() {
		var q = input.value.trim();
		var scope = allBox && allBox.checked ? "" : cfg.space || "";
		var key = q + "|" + scope;
		if (key === lastQ) return;
		lastQ = key;
		if (q.length < 2) {
			list.innerHTML = "";
			hint.textContent = "Type at least two characters. Use ↑ ↓ to move and Enter to open.";
			hint.hidden = false;
			return;
		}
		var my = ++seq;
		var url = "/api/method/thinknxg_docs.api.search?" + new URLSearchParams({ query: q, space: scope });
		fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
			.then(function (r) { return r.json(); })
			.then(function (d) { if (my === seq) render(d.message || [], q); })
			.catch(function () {
				if (my !== seq) return;
				list.innerHTML = "";
				hint.textContent = "Search isn't responding. Check your connection and try again.";
				hint.hidden = false;
			});
	}

	$$("[data-dx-search-open]").forEach(function (b) { b.addEventListener("click", openSearch); });
	$$("[data-dx-search-close]", modal).forEach(function (b) { b.addEventListener("click", closeSearch); });
	input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 160); });
	if (allBox) allBox.addEventListener("change", function () { lastQ = ""; run(); input.focus(); });
	input.addEventListener("keydown", function (e) {
		if (e.key === "ArrowDown") { e.preventDefault(); select(sel + 1); }
		else if (e.key === "ArrowUp") { e.preventDefault(); select(sel - 1); }
		else if (e.key === "Enter") {
			var a = $$("li", list)[sel];
			if (a) { e.preventDefault(); window.location.href = a.querySelector("a").href; }
		}
	});
	document.addEventListener("keydown", function (e) {
		var typing = /INPUT|TEXTAREA|SELECT/.test((e.target || {}).tagName || "") || (e.target || {}).isContentEditable;
		if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
			e.preventDefault();
			modal.hidden ? openSearch() : closeSearch();
		} else if (e.key === "/" && !typing && modal.hidden) {
			e.preventDefault();
			openSearch();
		} else if (e.key === "Escape" && !modal.hidden) {
			closeSearch();
		} else if (e.key === "Escape" && document.body.classList.contains("dx-nav-open")) {
			setDrawer(false);
		}
	});
})();
