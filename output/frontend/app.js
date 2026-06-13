(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const fmt = window.DesertVis.formatNumber;
  let store = null;
  let contract = null;
  let playTimer = null;
  let resizeTimer = null;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusLabel(status) {
    if (status === "ok") return "Green: reliable";
    if (status === "warn") return "Yellow: fragile";
    if (status === "bad") return "Red: review";
    return "Not classified";
  }

  function statusClass(status) {
    return status === "ok" || status === "warn" || status === "bad" ? status : "neutral";
  }

  function statusColor(status) {
    const colors = window.DesertVis.colors || {};
    return colors[status] || colors.steel || "#64748b";
  }

  function caseMaxTime(caseData) {
    const eventMax = d3.max(caseData.events, (event) => event.day) || 0;
    return Math.max(eventMax, caseData.level.deadline || 0);
  }

  function nearestEvent(caseData, time) {
    if (!caseData.events.length) return null;
    const current = Number(time);
    const exact = caseData.events.find((event) => event.day === current);
    if (exact) return exact;
    const previous = caseData.events.filter((event) => event.day <= current).at(-1);
    return previous || caseData.events[0];
  }

  function selectedCase(state) {
    return contract.caseMap.get(state.selectedCase) || contract.cases[0];
  }

  function selectedScenario(caseData, state) {
    if (!state.selectedScenario) return null;
    return caseData.scenarioPoints.find((point) => point.id === state.selectedScenario) || null;
  }

  function showTooltip(event, html) {
    const tooltip = $("tooltip");
    tooltip.innerHTML = html;
    tooltip.style.left = `${event.clientX + 12}px`;
    tooltip.style.top = `${event.clientY + 12}px`;
    tooltip.style.opacity = "1";
  }

  function hideTooltip() {
    $("tooltip").style.opacity = "0";
  }

  function renderCaseSelector(state) {
    const select = $("caseSelect");
    select.innerHTML = contract.cases.map((item) => (
      `<option value="${escapeHtml(item.id)}"${item.id === state.selectedCase ? " selected" : ""}>${escapeHtml(item.label)}</option>`
    )).join("");
    select.onchange = (event) => {
      stopReplay();
      const nextCase = contract.caseMap.get(event.target.value);
      store.setState({
        selectedCase: event.target.value,
        currentTime: 0,
        selectedEvent: nextCase && nextCase.events[0] ? nextCase.events[0].id : null,
        selectedScenario: null,
        selectedLabel: null,
        selectedTrack: null,
        selectedTemplate: null,
        comparisonSelection: null,
        brushRange: null,
        filterState: { quality: "all" }
      });
    };
  }

  function renderHeader(caseData) {
    const globalStatus = $("globalStatus");
    globalStatus.className = `status-chip ${statusClass(caseData.qualityStatus)}`;
    globalStatus.textContent = statusLabel(caseData.qualityStatus);
  }

  function renderKPIs(caseData) {
    $("kpiStrip").innerHTML = (caseData.kpiItems || []).map((item) => {
      const rawValue = typeof item.value === "number" ? fmt(item.value, item.digits || 0) : item.value;
      const value = item.id === "quality" ? statusLabel(rawValue) : rawValue;
      const toneClass = item.tone && item.tone !== "neutral" ? ` ${statusClass(item.tone)}` : "";
      return `
        <span class="kpi-chip kpi-${escapeHtml(item.id)}${toneClass}">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </span>
      `;
    }).join("");
  }

  function renderLegend() {
    const entries = [
      ["action", "actions"],
      ["pressure", "hot / mine / pressure"],
      ["ok", "ok / feasible"],
      ["warn", "fragile"],
      ["bad", "storm / failure"],
      ["current", "current / selected"]
    ];
    $("semanticLegend").innerHTML = entries.map(([key, label]) => `
      <span class="legend-pill ${key}">
        ${escapeHtml(label)}
      </span>
    `).join("");
  }

  function setDiagnostics(expanded) {
    const body = document.querySelector(".diagnostics-body");
    const icon = $("diagnosticsIcon");
    if (!body) return;
    body.classList.toggle("expanded", expanded);
    if (icon) icon.textContent = expanded ? "-" : "+";
  }

  function renderFilterPanel(caseData, state) {
    const actions = Object.keys(caseData.stats.actionCounts || {});
    const labelButtons = [{ key: "", label: "All actions" }]
      .concat(actions.map((action) => ({ key: action, label: window.DesertVis.summarizeAction(action) })));
    $("labelFilterPanel").innerHTML = labelButtons.map((item) => `
      <button type="button" class="${(state.selectedLabel || "") === item.key ? "active" : ""}" data-label="${escapeHtml(item.key)}">
        ${escapeHtml(item.label)}
      </button>
    `).join("");
    $("labelFilterPanel").querySelectorAll("button").forEach((button) => {
      button.onclick = () => store.setState({
        selectedLabel: button.dataset.label || null,
        selectedTemplate: null
      });
    });

    const quality = state.filterState && state.filterState.quality ? state.filterState.quality : "all";
    $("qualityFilterPanel").innerHTML = ["all", "ok", "warn", "bad"].map((item) => `
      <button type="button" class="${quality === item ? "active" : ""}" data-quality="${item}">
        ${item === "all" ? "All quality" : statusLabel(item).split(":")[0]}
      </button>
    `).join("");
    $("qualityFilterPanel").querySelectorAll("button").forEach((button) => {
      button.onclick = () => store.setState({
        filterState: { ...(state.filterState || {}), quality: button.dataset.quality },
        selectedTemplate: null
      });
    });
  }

  function renderSchemaPanel() {
    const groups = [
      ["time", contract.schema.time],
      ["category", contract.schema.category],
      ["coordinate", contract.schema.coordinate],
      ["quality", contract.schema.quality],
      ["trajectory", contract.schema.trajectory],
      ["projection", contract.schema.projection],
      ["video", contract.schema.video]
    ];
    $("fieldSchemaPanel").innerHTML = groups.map(([name, fields]) => `
      <div class="schema-row">
        <div class="schema-key">${escapeHtml(name)}</div>
        <div class="schema-values">${fields.length ? fields.map(escapeHtml).join(", ") : "missing"}</div>
      </div>
    `).join("");
  }

  function filteredTemplates(caseData, state) {
    const quality = state.filterState && state.filterState.quality ? state.filterState.quality : "all";
    return caseData.templateRows.filter((row) => {
      const qualityOk = quality === "all" || row.status === quality;
      const labelOk = !state.selectedLabel || row.filter.selectedLabel === state.selectedLabel || row.type !== "action template";
      return qualityOk && labelOk;
    });
  }

  function renderTemplateTable(caseData, state) {
    const rows = filteredTemplates(caseData, state);
    if (!rows.length) {
      $("templateTable").innerHTML = `<div class="empty-copy">No template rows match the active filters.</div>`;
      return;
    }
    $("templateTable").innerHTML = `
      <table class="compact-table">
        <thead>
          <tr>
            <th>Template</th>
            <th>Type</th>
            <th>Support</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => {
            const total = d3.sum(row.segments || [], (segment) => segment.value) || 1;
            const bars = (row.segments || []).map((segment) => `
              <span style="width:${Math.max(5, segment.value / total * 100)}%;background:${statusColor(segment.status)}" title="${escapeHtml(segment.label)}"></span>
            `).join("");
            return `
              <tr class="${state.selectedTemplate === row.id ? "selected" : ""}" data-template-id="${escapeHtml(row.id)}">
                <td>
                  <div class="template-name">${escapeHtml(row.label)}</div>
                  <div class="template-bars">${bars}</div>
                </td>
                <td>${escapeHtml(row.type)}</td>
                <td>${escapeHtml(row.metric)}</td>
                <td><span class="tiny-status ${statusClass(row.status)}">${escapeHtml(statusLabel(row.status).split(":")[0])}</span></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
    $("templateTable").querySelectorAll("tr[data-template-id]").forEach((rowEl) => {
      rowEl.onclick = () => {
        const row = caseData.templateRows.find((item) => item.id === rowEl.dataset.templateId);
        if (!row) return;
        const patch = {
          selectedTemplate: state.selectedTemplate === row.id ? null : row.id,
          selectedLabel: row.filter.selectedLabel || state.selectedLabel,
          filterState: row.filter.selectedQuality ? { ...(state.filterState || {}), quality: row.filter.selectedQuality } : state.filterState
        };
        if (row.filter.selectedScenarioStatus) {
          const ids = caseData.scenarioPoints
            .filter((point) => point.label === row.filter.selectedScenarioStatus)
            .map((point) => point.id);
          patch.brushRange = { caseId: caseData.id, ids };
          patch.selectedScenario = ids[0] || null;
        }
        store.setState(patch);
      };
      rowEl.onmousemove = (event) => {
        const row = caseData.templateRows.find((item) => item.id === rowEl.dataset.templateId);
        if (row) showTooltip(event, `${escapeHtml(row.label)}<br>${escapeHtml(row.evidence)}<br>Fields: ${escapeHtml(row.fields.join(", "))}`);
      };
      rowEl.onmouseleave = hideTooltip;
    });
  }

  function renderViewIndex(caseData, state) {
    $("viewIndex").innerHTML = caseData.viewSpecs.map((spec) => `
      <button type="button" class="view-card ${spec.available ? "available" : "missing"} ${state.selectedViewSpec === spec.id ? "active" : ""}" data-view-id="${escapeHtml(spec.id)}">
        <span class="view-title">${escapeHtml(spec.title)}</span>
        <span class="view-meta">${escapeHtml(spec.type)} / ${spec.available ? "available" : "unavailable"}</span>
      </button>
    `).join("");
    $("viewIndex").querySelectorAll("button").forEach((button) => {
      button.onclick = () => store.setState({ selectedViewSpec: button.dataset.viewId });
    });
  }

  function renderReplay(caseData, state) {
    const maxTime = caseMaxTime(caseData);
    const nextEvent = nearestEvent(caseData, state.currentTime);
    const activeReplayView = state.activeReplayView || "matrix";
    $("replayTitle").textContent = `${caseData.level.name || `Level ${caseData.id}`} Event Replay`;
    $("replayViewSwitch").innerHTML = [
      ["matrix", "Matrix"],
      ["timeline", "Timeline"],
      ["flow", "Flow"]
    ].map(([key, label]) => `
      <button type="button" class="${activeReplayView === key ? "active" : ""}" data-replay-view="${key}">
        ${label}
      </button>
    `).join("");
    $("replayViewSwitch").querySelectorAll("button").forEach((button) => {
      button.onclick = () => store.setState({ activeReplayView: button.dataset.replayView });
    });
    $("sequenceMatrixChart").classList.toggle("active", activeReplayView === "matrix");
    $("timelineChart").classList.toggle("active", activeReplayView === "timeline");
    $("comparisonFlowChart").classList.toggle("active", activeReplayView === "flow");
    $("sequenceMatrixChart").setAttribute("aria-hidden", activeReplayView === "matrix" ? "false" : "true");
    $("timelineChart").setAttribute("aria-hidden", activeReplayView === "timeline" ? "false" : "true");
    $("comparisonFlowChart").setAttribute("aria-hidden", activeReplayView === "flow" ? "false" : "true");
    $("currentTimeChip").textContent = `Day ${fmt(state.currentTime)}`;
    const slider = $("timeSlider");
    slider.max = String(maxTime);
    slider.value = String(Math.min(maxTime, Number(state.currentTime || 0)));
    slider.oninput = (eventInput) => {
      stopReplay();
      const nextTime = Number(eventInput.target.value);
      const event = nearestEvent(caseData, nextTime);
      store.setState({
        currentTime: nextTime,
        selectedEvent: event ? event.id : null
      });
    };

    const selected = state.brushRange && state.brushRange.caseId === caseData.id && state.brushRange.ids
      ? `${state.brushRange.ids.length} linked rows selected`
      : "no brush selection";
    $("sequenceStatus").textContent = selected;

    if (nextEvent && state.selectedEvent !== nextEvent.id && !state.selectedEvent) {
      store.setState({ selectedEvent: nextEvent.id });
    }
  }

  function renderSemantic(caseData, state) {
    const event = nearestEvent(caseData, state.currentTime);
    const blocks = [
      event ? {
        id: event.id,
        label: `Current trace row / Day ${event.day}`,
        text: `${event.label}, node ${fmt(event.node)}, weather ${event.weatherLabel}. ${event.evidence || "No additional evidence field."}`,
        time: event.day,
        kind: "event"
      } : null,
      ...caseData.semanticBlocks
    ].filter(Boolean);

    $("semanticStatus").textContent = caseData.missing.transcript ? "no transcript" : "timestamped";
    $("semanticList").innerHTML = blocks.map((block) => {
      const active = block.id === state.selectedEvent || block.time === state.currentTime;
      return `
        <article class="semantic-item${active ? " active" : ""}" data-id="${escapeHtml(block.id)}" data-time="${block.time ?? ""}">
          <div class="semantic-label">${escapeHtml(block.label)}</div>
          <div class="semantic-text">${escapeHtml(block.text)}</div>
        </article>
      `;
    }).join("");
    $("semanticList").querySelectorAll(".semantic-item").forEach((item) => {
      item.onclick = () => {
        const patch = { selectedEvent: item.dataset.id };
        if (item.dataset.time !== "") patch.currentTime = Number(item.dataset.time);
        store.setState(patch);
      };
    });
  }

  function renderDetails(caseData, state) {
    const event = nearestEvent(caseData, state.currentTime);
    const scenario = selectedScenario(caseData, state);
    const comparison = state.comparisonSelection && state.comparisonSelection.caseId === caseData.id ? state.comparisonSelection : null;
    const brushIds = state.brushRange && state.brushRange.caseId === caseData.id && state.brushRange.ids ? state.brushRange.ids : [];
    const rows = scenario ? [
      ["Selected scenario", scenario.scenario],
      ["Weather mix", `storm ${scenario.stormCount}, hot ${scenario.hotCount}, sunny ${scenario.sunnyCount}`],
      ["Status", `${scenario.label} / ${scenario.status}`],
      ["Objective", fmt(scenario.objective, 1)],
      ["Arrival", `day ${fmt(scenario.arrivalDay)}`],
      ["Brush size", brushIds.length ? `${brushIds.length} scenarios` : "none"]
    ] : [
      ["Selected event", event ? `Day ${event.day}` : "--"],
      ["Action", event ? event.label : "--"],
      ["Transition", event ? `${fmt(event.fromNode)} -> ${fmt(event.toNode)}` : "--"],
      ["Cash", event ? fmt(event.cash) : "--"],
      ["Consumption", event ? `W ${fmt(event.consumeWater)} / F ${fmt(event.consumeFood)}` : "--"],
      ["Linked flow", comparison ? `${comparison.source} -> ${comparison.target}` : "none"],
      ["Reliability", statusLabel(caseData.qualityStatus)],
      ["Missing fields", [caseData.missing.embedding ? "embedding" : "", caseData.missing.video ? "video" : "", caseData.missing.transcript ? "transcript" : ""].filter(Boolean).join(", ") || "none"]
    ];
    $("detailPanel").innerHTML = `
      <div class="kv-grid">
        ${rows.map(([label, value]) => `
          <div class="kv">
            <div class="kv-label">${escapeHtml(label)}</div>
            <div class="kv-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderStatuses(caseData) {
    $("spatialStatus").textContent = caseData.nodes.length && caseData.edges.length ? `${caseData.nodes.length} nodes` : "missing coords";
    const quality = $("qualityStatus");
    quality.className = `status-chip ${statusClass(caseData.qualityStatus)}`;
    quality.textContent = statusLabel(caseData.qualityStatus);
  }

  function renderQualityPanel(caseData) {
    $("qualityList").innerHTML = caseData.qualityItems.map((item) => `
      <button class="quality-row ${statusClass(item.status)}" type="button" data-quality-id="${escapeHtml(item.id)}">
        <span class="quality-row-title">${escapeHtml(item.label)}</span>
        <span class="quality-row-metric">${escapeHtml(item.metric)}</span>
      </button>
    `).join("");
    $("qualityList").querySelectorAll(".quality-row").forEach((button) => {
      button.onclick = () => {
        const item = caseData.qualityItems.find((quality) => quality.id === button.dataset.qualityId);
        if (item && item.time !== null && item.time !== undefined) {
          const event = nearestEvent(caseData, item.time);
          store.setState({ currentTime: item.time, selectedEvent: event ? event.id : null });
        }
      };
    });
    const summary = caseData.qualitySummary || {};
    $("qualityExplain").textContent = summary.primaryReason || "No reliability summary is available.";
  }

  function renderSources(caseData) {
    const sourceText = contract.sourceRows.length
      ? contract.sourceRows.map((row) => `${row.exists ? "ok" : "missing"} ${row.key}: ${row.path}`).join("\n")
      : "No source manifest was found.";
    const schemaText = [
      `time: ${contract.schema.time.join(", ")}`,
      `category: ${contract.schema.category.join(", ")}`,
      `coordinate: ${contract.schema.coordinate.join(", ")}`,
      `quality: ${contract.schema.quality.join(", ")}`,
      `trajectory: ${contract.schema.trajectory.join(", ")}`,
      `projection: ${contract.schema.projection.join(", ") || "missing embedding file"}`,
      `video: ${contract.schema.video.join(", ") || "missing video_path/video asset"}`
    ].join("\n");
    const missingText = Object.entries(caseData.missing)
      .filter(([, value]) => value)
      .map(([key, value]) => `${key}: ${value}`)
      .join("\n");
    $("sourcePanel").innerHTML = [
      ["Reviewed Sources", sourceText],
      ["Normalized Fields", schemaText],
      ["Missing / Downgraded Modalities", missingText || "No modality gaps for this case."]
    ].map(([title, text]) => `
      <div class="source-block">
        <div class="source-title">${escapeHtml(title)}</div>
        <div class="source-text">${escapeHtml(text).replace(/\n/g, "<br>")}</div>
      </div>
    `).join("");
  }

  function renderCharts(caseData, state) {
    const ui = { showTooltip, hideTooltip };
    window.DesertVis.renderSequenceMatrix($("sequenceMatrixChart"), caseData, state, store.setState, ui);
    window.DesertVis.renderTimeline($("timelineChart"), caseData, state, store.setState, ui);
    window.DesertVis.renderComparisonFlow($("comparisonFlowChart"), caseData, state, store.setState, ui);
    window.DesertVis.renderSpatial($("spatialChart"), caseData, state, store.setState, ui);
  }

  function render() {
    const state = store.getState();
    const caseData = selectedCase(state);
    if (!caseData) return;
    renderCaseSelector(state);
    renderHeader(caseData);
    renderKPIs(caseData);
    renderLegend();
    renderFilterPanel(caseData, state);
    renderSchemaPanel();
    renderTemplateTable(caseData, state);
    renderViewIndex(caseData, state);
    renderReplay(caseData, state);
    renderSemantic(caseData, state);
    renderDetails(caseData, state);
    renderStatuses(caseData);
    renderQualityPanel(caseData);
    renderSources(caseData);
    renderCharts(caseData, state);
  }

  function stopReplay() {
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
    $("playButton").textContent = "Play";
  }

  function toggleReplay() {
    if (playTimer) {
      stopReplay();
      return;
    }
    $("playButton").textContent = "Pause";
    playTimer = setInterval(() => {
      const state = store.getState();
      const caseData = selectedCase(state);
      const maxTime = caseMaxTime(caseData);
      const nextTime = Number(state.currentTime || 0) >= maxTime ? 0 : Number(state.currentTime || 0) + 1;
      const event = nearestEvent(caseData, nextTime);
      store.setState({ currentTime: nextTime, selectedEvent: event ? event.id : null });
    }, 750);
  }

  function init() {
    contract = window.DesertVis.normalize(window.DESERT_DASHBOARD_DATA || {});
    const firstCase = contract.cases[0];
    store = window.DesertVis.createInteractionState({
      selectedCase: firstCase ? firstCase.id : null,
      currentTime: 0,
      selectedTrack: null,
      selectedLabel: null,
      selectedEvent: firstCase && firstCase.events[0] ? firstCase.events[0].id : null,
      selectedScenario: null,
      selectedTemplate: null,
      selectedViewSpec: null,
      comparisonSelection: null,
      activeReplayView: "matrix",
      activePanel: "workspace",
      filterState: { quality: "all" },
      brushRange: null
    });
    $("playButton").onclick = toggleReplay;
    $("diagnosticsToggle").onclick = () => {
      const body = document.querySelector(".diagnostics-body");
      setDiagnostics(!(body && body.classList.contains("expanded")));
    };
    store.subscribe(render);
    render();
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(render, 120);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
