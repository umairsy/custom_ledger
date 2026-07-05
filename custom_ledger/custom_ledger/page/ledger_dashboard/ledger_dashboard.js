// Copyright (c) 2026, Custom Ledger Contributors
// License: TBD. See license.txt

frappe.pages["ledger-dashboard"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Ledger Dashboard"),
        single_column: true,
    });

    _ldg_inject_css();

    wrapper._ldg = new LedgerDashboard(wrapper);
};

frappe.pages["ledger-dashboard"].on_page_show = function (wrapper) {
    wrapper._ldg.on_show();
};

// ---------------------------------------------------------------------------
// Dashboard controller
// ---------------------------------------------------------------------------

function LedgerDashboard(wrapper) {
    this.wrapper = wrapper;
    this.$body = $(wrapper).find(".layout-main-section");
    this.config_name = null;
    this.meta = null;
    this.debounce_timer = null;
    this.link_ctrls = {};
    this.trend_chart = null;
    this.breakdown_chart = null;
    this.dist_chart = null;
}

LedgerDashboard.prototype.on_show = function () {
    var config = frappe.utils.get_url_arg("config");
    if (config !== this.config_name) {
        this.config_name = config || null;
        this.link_ctrls = {};
        this.trend_chart = null;
        this.breakdown_chart = null;
        this.dist_chart = null;
        this._init();
    }
};

LedgerDashboard.prototype._init = function () {
    var me = this;
    this.$body.html('<div class="ldg-loading">Loading…</div>');

    if (!this.config_name) {
        this.$body.html(
            '<div class="ldg-empty">No Ledger Config selected. ' +
            'Open a Ledger Config and click <strong>View Dashboard</strong>.</div>'
        );
        return;
    }

    frappe.call({
        method: "custom_ledger.custom_ledger.api.dashboard_data.get_dashboard_meta",
        args: { config_name: me.config_name },
        callback: function (r) {
            if (!r.message) return;
            me.meta = r.message;
            me.wrapper.page.set_title(
                frappe.utils.escape_html(me.meta.ledger_name) + " — Dashboard"
            );
            me._render_shell();
            me._render_filter_bar();
            me._load_data();
        },
    });
};

// ---------------------------------------------------------------------------
// Shell
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_shell = function () {
    this.$body.html(
        '<div class="ldg-dashboard">' +
            '<div id="ldg-filters"></div>' +
            '<div class="ldg-kpi-strip" id="ldg-kpi"></div>' +
            '<div class="ldg-chart-row ldg-full">' +
                '<div class="ldg-chart-card">' +
                    '<div class="ldg-chart-title">' + __("Balance Over Time") + '</div>' +
                    '<div id="ldg-trend"></div>' +
                '</div>' +
            '</div>' +
            '<div class="ldg-chart-row" id="ldg-mid-row">' +
                '<div class="ldg-chart-card ldg-half" id="ldg-breakdown-card">' +
                    '<div class="ldg-chart-title">' + __("Breakdown by Group") + '</div>' +
                    '<div id="ldg-breakdown"></div>' +
                '</div>' +
                '<div class="ldg-chart-card ldg-half">' +
                    '<div class="ldg-chart-title">' + __("Top Movers") + '</div>' +
                    '<div id="ldg-top-movers"></div>' +
                '</div>' +
            '</div>' +
            '<div class="ldg-chart-row">' +
                '<div class="ldg-chart-card ldg-half" id="ldg-dist-card">' +
                    '<div class="ldg-chart-title">' + __("Delta Distribution") + '</div>' +
                    '<div id="ldg-dist-subtitle" class="ldg-subtitle"></div>' +
                    '<div id="ldg-distribution"></div>' +
                '</div>' +
                '<div class="ldg-chart-card ldg-half">' +
                    '<div class="ldg-chart-title">' + __("Activity Heatmap") + '</div>' +
                    '<div id="ldg-heatmap"></div>' +
                '</div>' +
            '</div>' +
        '</div>'
    );
};

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_filter_bar = function () {
    var me = this;
    var meta = this.meta;

    // Primary record filter: Carrier for Type 2, Source Document for Type 1.
    // The key must match the backend filter (carrier_name / source_name).
    var is_type2 = meta.ledger_type === "Track balance from transactions";
    me._primary_key = is_type2 ? "carrier_name" : "source_name";
    me._primary_doctype = (is_type2 ? meta.balance_carrier_doctype : meta.source_doctype) || "";

    var today_str = frappe.datetime.get_today();
    var from_str = frappe.datetime.month_start();

    // Group-by options
    var grp_opts =
        '<option value="none">' + __("None (Aggregate)") + "</option>" +
        '<option value="source">' + __("Source Document") + "</option>";
    if (meta.narration_field) {
        grp_opts += '<option value="narration">' + __("Narration") + "</option>";
    }
    meta.dimensions.forEach(function (d, i) {
        grp_opts += '<option value="dim_' + (i + 1) + '">' +
            frappe.utils.escape_html(d.label) + "</option>";
    });

    var default_group =
        meta.dimensions.length > 0 ? "dim_1" :
        meta.narration_field ? "narration" :
        "source";

    // Dimension filter slots
    var dim_slots = meta.dimensions
        .map(function (d, i) {
            return (
                '<div class="ldg-filter-item" id="ldg-dim-' + (i + 1) + '-wrap">' +
                    "<label>" + frappe.utils.escape_html(d.label) + "</label>" +
                    '<div id="ldg-dim-' + (i + 1) + '-ctrl" class="ldg-link-wrap"></div>' +
                "</div>"
            );
        })
        .join("");

    var html =
        '<div class="ldg-filter-bar">' +
            '<div class="ldg-filter-item">' +
                "<label>" + __("From Date") + "</label>" +
                '<input type="date" id="ldg-from-date" value="' + from_str + '">' +
            "</div>" +
            '<div class="ldg-filter-item">' +
                "<label>" + __("To Date") + "</label>" +
                '<input type="date" id="ldg-to-date" value="' + today_str + '">' +
            "</div>" +
            '<div class="ldg-filter-item">' +
                "<label>" + __("Time Grain") + "</label>" +
                '<select id="ldg-grain">' +
                    '<option value="day">' + __("Day") + "</option>" +
                    '<option value="week">' + __("Week") + "</option>" +
                    '<option value="month">' + __("Month") + "</option>" +
                    '<option value="quarter">' + __("Quarter") + "</option>" +
                    '<option value="year">' + __("Year") + "</option>" +
                "</select>" +
            "</div>" +
            '<div class="ldg-filter-item">' +
                "<label>" + __("Group By") + "</label>" +
                '<select id="ldg-group-by">' + grp_opts + "</select>" +
            "</div>" +
            '<div class="ldg-filter-item" id="ldg-primary-wrap">' +
                "<label>" + frappe.utils.escape_html(me._primary_doctype) + "</label>" +
                '<div id="ldg-primary-ctrl" class="ldg-link-wrap"></div>' +
            "</div>" +
            dim_slots +
        "</div>";

    $("#ldg-filters").html(html);

    // Set default group-by
    $("#ldg-group-by").val(default_group);

    // Attach frappe Link controls
    if (me._primary_doctype) {
        me.link_ctrls[me._primary_key] = me._make_link_ctrl("ldg-primary-ctrl", me._primary_doctype);
    }
    meta.dimensions.forEach(function (d, i) {
        me.link_ctrls["dim_" + (i + 1)] = me._make_link_ctrl(
            "ldg-dim-" + (i + 1) + "-ctrl",
            d.link_doctype
        );
    });

    // Events
    $("#ldg-from-date, #ldg-to-date").on("change", function () {
        me._update_grain_options();
        me._on_filter_change();
    });
    $("#ldg-grain, #ldg-group-by").on("change", function () {
        me._on_filter_change();
    });
};

LedgerDashboard.prototype._make_link_ctrl = function (container_id, doctype) {
    var me = this;
    var el = document.getElementById(container_id);
    if (!el) return null;

    try {
        var ctrl = frappe.ui.form.make_control({
            parent: el,
            df: {
                fieldtype: "Link",
                fieldname: container_id,
                label: "",
                options: doctype,
            },
            render_input: true,
            only_input: true,
        });
        ctrl.refresh();
        ctrl.$input.addClass("ldg-link-input").on("change", function () {
            me._on_filter_change();
        });
        // Also fire on awesomplete selection
        ctrl.$input[0].addEventListener("awesomplete-selectcomplete", function () {
            setTimeout(function () { me._on_filter_change(); }, 50);
        });
        return ctrl;
    } catch (err) {
        // Fallback to plain text input if frappe control init fails
        $(el).html(
            '<input type="text" class="form-control input-xs ldg-link-input" ' +
            'placeholder="' + frappe.utils.escape_html(doctype) + '">'
        );
        $(el).find("input").on("change blur", function () { me._on_filter_change(); });
        return null;
    }
};

LedgerDashboard.prototype._update_grain_options = function () {
    var from = $("#ldg-from-date").val();
    var to = $("#ldg-to-date").val();
    if (!from || !to) return;

    var days = frappe.datetime.get_day_diff(to, from);
    var $grain = $("#ldg-grain");
    $grain.find('option[value="day"]').prop("disabled", days > 180);
    $grain.find('option[value="hour"]').prop("disabled", days > 7);

    if ($grain.find(":selected").prop("disabled")) {
        $grain.find("option:not(:disabled)").first().prop("selected", true);
    }
};

LedgerDashboard.prototype._on_filter_change = function () {
    var me = this;
    clearTimeout(this.debounce_timer);
    this.debounce_timer = setTimeout(function () { me._load_data(); }, 300);
};

// ---------------------------------------------------------------------------
// Collect filters
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._get_filters = function () {
    var me = this;
    var f = {
        from_date: $("#ldg-from-date").val(),
        to_date: $("#ldg-to-date").val(),
        time_grain: $("#ldg-grain").val() || "day",
        group_by: $("#ldg-group-by").val() || "none",
    };

    function read_ctrl(key, ctrl_id_suffix) {
        var ctrl = me.link_ctrls[key];
        if (ctrl && ctrl.get_value) {
            var v = ctrl.get_value();
            if (v) f[key] = v;
        } else {
            var v2 = $("#" + ctrl_id_suffix + " input").val();
            if (v2) f[key] = v2;
        }
    }

    read_ctrl(me._primary_key, "ldg-primary-ctrl");
    me.meta.dimensions.forEach(function (d, i) {
        read_ctrl("dim_" + (i + 1), "ldg-dim-" + (i + 1) + "-ctrl");
    });

    return f;
};

// ---------------------------------------------------------------------------
// Load + dispatch
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._load_data = function () {
    var me = this;
    var f = this._get_filters();

    // Show inline spinners in each chart area without clearing the cards
    $(".ldg-chart-card .ldg-chart-body, #ldg-kpi").html('<div class="ldg-loading">' + __("Loading…") + "</div>");

    frappe.call({
        method: "custom_ledger.custom_ledger.api.dashboard_data.get_dashboard_data",
        args: { config_name: me.config_name, filters: JSON.stringify(f) },
        callback: function (r) {
            if (!r.message) return;
            var d = r.message;
            var prec = me.meta.precision;
            me._render_kpi(d.kpi, prec);
            me._render_trend(d.trend);
            me._render_breakdown(d.breakdown, f.group_by);
            me._render_top_movers(d.top_movers, prec);
            me._render_distribution(d.distribution);
            me._render_heatmap(d.heatmap);
        },
    });
};

// ---------------------------------------------------------------------------
// KPI Strip
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_kpi = function (kpi, prec) {
    function fmt(n) {
        return parseFloat(n || 0).toLocaleString(undefined, {
            minimumFractionDigits: prec,
            maximumFractionDigits: prec,
        });
    }
    var sign = kpi.net_change > 0 ? "+" : "";
    var nc_col =
        kpi.net_change > 0 ? "#0F6E56" :
        kpi.net_change < 0 ? "#993C1D" :
        "var(--text-color)";

    $("#ldg-kpi").html(
        _kpi_tile(__("Closing Balance"), fmt(kpi.closing), "") +
        _kpi_tile(__("Net Change"), sign + fmt(kpi.net_change), "color:" + nc_col) +
        _kpi_tile(__("Total In"), "+" + fmt(kpi.total_in), "color:#0F6E56") +
        _kpi_tile(__("Total Out"), "−" + fmt(kpi.total_out), "color:#993C1D") +
        _kpi_tile(__("Records"), kpi.records, "")
    );
};

function _kpi_tile(label, value, style) {
    return (
        '<div class="ldg-kpi-tile">' +
            '<div class="ldg-kpi-label">' + label + "</div>" +
            '<div class="ldg-kpi-value"' + (style ? ' style="' + style + '"' : "") + ">" +
                value +
            "</div>" +
        "</div>"
    );
}

// ---------------------------------------------------------------------------
// Trend Chart
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_trend = function (data) {
    var $wrap = $("#ldg-trend");
    $wrap.empty();

    if (!data || !data.labels || !data.labels.length || !data.datasets || !data.datasets.length) {
        $wrap.html('<div class="ldg-empty">' + __("No data in this period.") + "</div>");
        return;
    }

    // Frappe Charts can't update in place reliably — recreate
    try {
        this.trend_chart = new frappe.Chart($wrap[0], {
            type: "line",
            data: { labels: data.labels, datasets: data.datasets },
            height: 280,
            colors: data.colors || ["#5DCAA5"],
            lineOptions: { hideDots: data.labels.length > 60 ? 1 : 0, regionFill: 0 },
            axisOptions: { xIsSeries: true },
            tooltipOptions: { formatTooltipX: function (d) { return d; } },
        });
    } catch (e) {
        $wrap.html('<div class="ldg-empty">' + __("Chart unavailable.") + "</div>");
    }
};

// ---------------------------------------------------------------------------
// Breakdown
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_breakdown = function (data, group_by) {
    var $card = $("#ldg-breakdown-card");
    var $wrap = $("#ldg-breakdown");

    if (data.hide || group_by === "none" || group_by === "narration") {
        $card.hide();
        return;
    }
    $card.show();
    $wrap.empty();

    if (!data.labels || !data.labels.length) {
        $wrap.html('<div class="ldg-empty">' + __("No data in this period.") + "</div>");
        return;
    }

    try {
        this.breakdown_chart = new frappe.Chart($wrap[0], {
            type: "bar",
            data: { labels: data.labels, datasets: [{ values: data.values }] },
            height: 260,
            colors: ["#5DCAA5"],
        });
    } catch (e) {
        $wrap.html('<div class="ldg-empty">' + __("Chart unavailable.") + "</div>");
    }
};

// ---------------------------------------------------------------------------
// Top Movers
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_top_movers = function (data, prec) {
    var $wrap = $("#ldg-top-movers");
    var cfg = this.config_name;

    if (data.hide) {
        $wrap.html('<div class="ldg-empty">' + __("Not enough data (min. 3 entries).") + "</div>");
        return;
    }

    function fmt_delta(d) {
        var sign = d >= 0 ? "+" : "";
        return sign + parseFloat(d || 0).toLocaleString(undefined, {
            minimumFractionDigits: prec, maximumFractionDigits: prec,
        });
    }

    function render_table(rows, cls, header) {
        var header_html =
            '<div class="ldg-movers-header ' + cls + '">' + header + "</div>";
        if (!rows || !rows.length) {
            return (
                '<div class="ldg-movers-table">' +
                header_html +
                '<div class="ldg-empty" style="padding:8px 0">' + __("None") + "</div>" +
                "</div>"
            );
        }
        var rows_html = rows
            .map(function (row) {
                var report_url =
                    "/app/query-report/Custom%20Ledger?ledger_config=" +
                    encodeURIComponent(cfg) +
                    "&source_name=" + encodeURIComponent(row.source_name) +
                    "&from_date=" + encodeURIComponent(row.date) +
                    "&to_date=" + encodeURIComponent(row.date);
                var src_url =
                    "/app/" +
                    frappe.router.slug(row.source_doctype) +
                    "/" +
                    encodeURIComponent(row.source_name);
                var dc = row.delta >= 0 ? "positive" : "negative";
                return (
                    '<div class="ldg-movers-row">' +
                        '<span class="ldg-movers-date" ' +
                            'onclick="window.open(\'' + _esc_attr(report_url) + '\',\'_blank\')" ' +
                            'title="' + __("Open in report") + '">' +
                            frappe.utils.escape_html(row.date) +
                        "</span>" +
                        "<a class=\"ldg-movers-source\" href=\"" + _esc_attr(src_url) + "\" " +
                            "target=\"_blank\" title=\"" + _esc_attr(row.source_name) + "\">" +
                            frappe.utils.escape_html(row.source_name) +
                        "</a>" +
                        '<span class="ldg-movers-delta ' + dc + '">' +
                            frappe.utils.escape_html(fmt_delta(row.delta)) +
                        "</span>" +
                    "</div>"
                );
            })
            .join("");
        return (
            '<div class="ldg-movers-table">' + header_html + rows_html + "</div>"
        );
    }

    $wrap.html(
        '<div class="ldg-movers-wrap">' +
            render_table(data.increases, "positive", __("Top Increases")) +
            render_table(data.decreases, "negative", __("Top Decreases")) +
        "</div>"
    );
};

// ---------------------------------------------------------------------------
// Distribution
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_distribution = function (data) {
    var $card = $("#ldg-dist-card");
    var $sub = $("#ldg-dist-subtitle");
    var $wrap = $("#ldg-distribution");

    if (data.hide) {
        $card.hide();
        return;
    }
    $card.show();
    $sub.text(data.subtitle || "");
    $wrap.empty();

    if (!data.labels || !data.labels.length) {
        $wrap.html('<div class="ldg-empty">' + __("No data.") + "</div>");
        return;
    }

    try {
        this.dist_chart = new frappe.Chart($wrap[0], {
            type: "bar",
            data: { labels: data.labels, datasets: [{ values: data.values }] },
            height: 200,
            colors: ["#6BB5E5"],
        });
    } catch (e) {
        $wrap.html('<div class="ldg-empty">' + __("Chart unavailable.") + "</div>");
    }
};

// ---------------------------------------------------------------------------
// Activity Heatmap
// ---------------------------------------------------------------------------

LedgerDashboard.prototype._render_heatmap = function (data) {
    var $wrap = $("#ldg-heatmap");

    if (!data || !data.data) {
        $wrap.html('<div class="ldg-empty">' + __("No data.") + "</div>");
        return;
    }

    function lerp(c1, c2, t) {
        function parse(h) {
            var m = /^#([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(h);
            return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
        }
        var a = parse(c1), b = parse(c2);
        return (
            "rgb(" +
            [0, 1, 2].map(function (i) { return Math.round(a[i] + (b[i] - a[i]) * t); }).join(",") +
            ")"
        );
    }
    var COLD = "#E6F1FB", HOT = "#185FA5";

    if (data.mode === "strip") {
        var max_c = Math.max.apply(null, data.data.concat([1]));
        var cells = data.days
            .map(function (day, i) {
                var cnt = data.data[i] || 0;
                var t = cnt / max_c;
                var bg = cnt > 0 ? lerp(COLD, HOT, t) : "#f0f0f0";
                var fg = t > 0.5 ? "#fff" : "#333";
                return (
                    '<div class="ldg-hm-strip-cell" style="background:' + bg + ';color:' + fg + '" ' +
                        'title="' + frappe.utils.escape_html(day) + ": " + cnt + " entries\">" +
                        '<div class="ldg-hm-strip-day">' + day + "</div>" +
                        '<div class="ldg-hm-strip-cnt">' + cnt + "</div>" +
                    "</div>"
                );
            })
            .join("");
        $wrap.html('<div class="ldg-hm-strip">' + cells + "</div>");
    } else {
        var flat = [].concat.apply([], data.data);
        var max_f = Math.max.apply(null, flat.concat([1]));
        var rows = data.days
            .map(function (day, di) {
                var cells = "";
                for (var h = 0; h < 24; h++) {
                    var cnt = data.data[di][h] || 0;
                    var t = cnt / max_f;
                    var bg = cnt > 0 ? lerp(COLD, HOT, t) : "#f0f0f0";
                    cells +=
                        '<div class="ldg-hm-cell" style="background:' + bg + '" ' +
                            'title="' + day + " " + h + ":00 — " + cnt + " entries\"></div>";
                }
                return (
                    '<div class="ldg-hm-row">' +
                        '<span class="ldg-hm-label">' + day + "</span>" +
                        cells +
                    "</div>"
                );
            })
            .join("");

        // Hour axis labels (every 4 hours)
        var hour_labels = '<div class="ldg-hm-row ldg-hm-hours"><span class="ldg-hm-label"></span>';
        for (var h = 0; h < 24; h++) {
            hour_labels +=
                '<div class="ldg-hm-cell" style="background:transparent;color:var(--text-muted);font-size:9px;text-align:center">' +
                (h % 4 === 0 ? h : "") +
                "</div>";
        }
        hour_labels += "</div>";

        $wrap.html('<div class="ldg-heatmap-grid">' + rows + hour_labels + "</div>");
    }
};

// ---------------------------------------------------------------------------
// CSS injection
// ---------------------------------------------------------------------------

function _ldg_inject_css() {
    if (document.getElementById("ldg-css")) return;
    var s = document.createElement("style");
    s.id = "ldg-css";
    s.textContent = [
        ".ldg-dashboard{padding:12px 0}",
        ".ldg-loading{color:var(--text-muted);text-align:center;padding:24px;font-size:13px}",
        ".ldg-empty{color:var(--text-muted);text-align:center;padding:40px 0;font-size:13px}",

        // Filter bar
        ".ldg-filter-bar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px;" +
            "align-items:flex-end;padding:12px 14px;background:var(--subtle-accent);" +
            "border:1px solid var(--border-color);border-radius:6px}",
        ".ldg-filter-item label{display:block;font-size:10px;color:var(--text-muted);" +
            "margin-bottom:3px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}",
        ".ldg-filter-item input[type=date],.ldg-filter-item select{height:30px;" +
            "border:1px solid var(--border-color);border-radius:4px;padding:0 7px;" +
            "font-size:12px;background:var(--card-bg);color:var(--text-color)}",
        ".ldg-link-wrap .frappe-control{margin-bottom:0}",
        ".ldg-link-wrap .form-control,.ldg-link-input{height:30px;font-size:12px;min-width:140px}",

        // KPI strip
        ".ldg-kpi-strip{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}",
        ".ldg-kpi-tile{flex:1;min-width:120px;background:var(--card-bg);" +
            "border:1px solid var(--border-color);border-radius:8px;padding:14px 12px;text-align:center}",
        ".ldg-kpi-label{font-size:10px;color:var(--text-muted);text-transform:uppercase;" +
            "letter-spacing:.05em;margin-bottom:6px;font-weight:600}",
        ".ldg-kpi-value{font-size:20px;font-weight:700;color:var(--text-color)}",

        // Chart cards
        ".ldg-chart-row{display:flex;gap:14px;margin-bottom:14px}",
        ".ldg-chart-row.ldg-full{flex-direction:column}",
        ".ldg-chart-card{background:var(--card-bg);border:1px solid var(--border-color);" +
            "border-radius:8px;padding:14px;flex:1;min-width:0}",
        ".ldg-half{flex:1}",
        ".ldg-chart-title{font-size:10px;font-weight:700;color:var(--text-muted);" +
            "text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px}",
        ".ldg-subtitle{font-size:11px;color:var(--text-muted);margin-bottom:6px}",

        // Top Movers
        ".ldg-movers-wrap{display:flex;gap:14px}",
        ".ldg-movers-table{flex:1;min-width:0}",
        ".ldg-movers-header{font-size:10px;font-weight:700;text-transform:uppercase;" +
            "letter-spacing:.05em;padding-bottom:5px;margin-bottom:6px;border-bottom:2px solid}",
        ".ldg-movers-header.positive{color:#0F6E56;border-color:#0F6E56}",
        ".ldg-movers-header.negative{color:#993C1D;border-color:#993C1D}",
        ".ldg-movers-row{display:flex;gap:6px;padding:4px 0;border-bottom:1px solid var(--border-color);font-size:11px;align-items:center}",
        ".ldg-movers-row:last-child{border-bottom:none}",
        ".ldg-movers-date{color:var(--text-muted);white-space:nowrap;cursor:pointer;flex-shrink:0}",
        ".ldg-movers-date:hover{color:var(--primary);text-decoration:underline}",
        ".ldg-movers-source{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" +
            "color:var(--primary);text-decoration:none}",
        ".ldg-movers-source:hover{text-decoration:underline}",
        ".ldg-movers-delta{font-weight:700;white-space:nowrap;flex-shrink:0}",
        ".ldg-movers-delta.positive{color:#0F6E56}",
        ".ldg-movers-delta.negative{color:#993C1D}",

        // Heatmap — strip mode
        ".ldg-hm-strip{display:flex;gap:4px;flex-wrap:wrap}",
        ".ldg-hm-strip-cell{border-radius:4px;padding:8px 6px;text-align:center;min-width:44px;flex:1}",
        ".ldg-hm-strip-day{font-size:10px;font-weight:600}",
        ".ldg-hm-strip-cnt{font-size:14px;font-weight:700}",

        // Heatmap — full grid
        ".ldg-heatmap-grid{overflow-x:auto}",
        ".ldg-hm-row{display:flex;align-items:center;margin-bottom:2px}",
        ".ldg-hm-label{width:30px;font-size:10px;color:var(--text-muted);flex-shrink:0}",
        ".ldg-hm-cell{width:22px;height:18px;margin:0 1px;border-radius:2px;flex-shrink:0}",
    ].join("\n");
    document.head.appendChild(s);
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function _esc_attr(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
