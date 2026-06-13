(function () {
  "use strict";

  const colors = {
    blue: "#3f6f9f",
    blueDark: "#2f5278",
    steel: "#64748b",
    line: "#d1d5db",
    grid: "#eef2f7",
    ink: "#111827",
    muted: "#6b7280",
    move: "#3f6f9f",
    stay: "#64748b",
    mine: "#9a7b36",
    buy_start: "#4f7f5f",
    unknown: "#9ca3af",
    sunny: "#4f7f5f",
    hot: "#9a7b36",
    storm: "#a45b50",
    none: "#9ca3af",
    ok: "#4f7f5f",
    warn: "#9a7b36",
    bad: "#a45b50"
  };

  function fmt(value, digits = 0) {
    return window.DesertVis.formatNumber(value, digits);
  }

  function clear(svgEl) {
    d3.select(svgEl).selectAll("*").remove();
  }

  function size(svgEl, minWidth = 320, minHeight = 220) {
    const rect = svgEl.getBoundingClientRect();
    return {
      width: Math.max(minWidth, rect.width || minWidth),
      height: Math.max(minHeight, rect.height || minHeight)
    };
  }

  function empty(svgEl, message) {
    clear(svgEl);
    const { width, height } = size(svgEl);
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    svg.append("foreignObject")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", width)
      .attr("height", height)
      .append("xhtml:div")
      .attr("class", "empty-state")
      .text(message);
  }

  function addGrid(svg, yScale, margin, width) {
    const ticks = yScale.ticks ? yScale.ticks(5) : [];
    svg.append("g")
      .selectAll("line")
      .data(ticks)
      .join("line")
      .attr("class", "grid-line")
      .attr("x1", margin.left)
      .attr("x2", width - margin.right)
      .attr("y1", (d) => yScale(d))
      .attr("y2", (d) => yScale(d));
  }

  function tooltip(ui, event, html) {
    if (ui && ui.showTooltip) ui.showTooltip(event, html);
  }

  function hideTooltip(ui) {
    if (ui && ui.hideTooltip) ui.hideTooltip();
  }

  function actionColor(action) {
    return colors[action] || colors.unknown;
  }

  function weatherColor(weather) {
    if (weather === "晴朗") return colors.sunny;
    if (weather === "高温") return colors.hot;
    if (weather === "沙暴") return colors.storm;
    return colors.none;
  }

  function statusColor(status) {
    return colors[status] || colors.steel;
  }

  function selectedEvent(caseData, state) {
    if (state.selectedEvent) {
      const found = caseData.events.find((event) => event.id === state.selectedEvent);
      if (found) return found;
    }
    const currentTime = Number(state.currentTime || 0);
    return caseData.events.find((event) => event.day === currentTime)
      || caseData.events.filter((event) => event.day <= currentTime).at(-1)
      || caseData.events[0]
      || null;
  }

  function renderDistribution(svgEl, caseData, state, setState, ui) {
    const events = caseData.events || [];
    const scenarioPoints = caseData.scenarioPoints || [];
    let rows = [];
    let title = "Action count";
    if (events.length) {
      const counts = d3.rollups(events, (items) => items.length, (item) => item.action);
      rows = counts.map(([key, value]) => ({
        key,
        label: window.DesertVis.summarizeAction(key),
        value,
        color: actionColor(key)
      }));
    } else if (scenarioPoints.length) {
      title = "Scenario status";
      const counts = d3.rollups(scenarioPoints, (items) => items.length, (item) => item.feasible ? "feasible" : "infeasible");
      rows = counts.map(([key, value]) => ({
        key,
        label: key,
        value,
        color: key === "feasible" ? colors.ok : colors.bad
      }));
    }
    if (!rows.length) {
      empty(svgEl, "No action, event, or scenario rows are available for this case.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 320, 120);
    const margin = { top: 18, right: 18, bottom: 28, left: 34 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const x = d3.scaleBand().domain(rows.map((d) => d.label)).range([margin.left, width - margin.right]).padding(0.24);
    const y = d3.scaleLinear().domain([0, d3.max(rows, (d) => d.value) || 1]).nice().range([height - margin.bottom, margin.top]);
    addGrid(svg, y, margin, width);
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).tickSizeOuter(0));
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(4).tickSizeOuter(0));
    svg.append("text")
      .attr("x", margin.left)
      .attr("y", 12)
      .attr("fill", colors.muted)
      .attr("font-size", 11)
      .text(title);
    svg.append("g")
      .selectAll("rect")
      .data(rows)
      .join("rect")
      .attr("x", (d) => x(d.label))
      .attr("y", (d) => y(d.value))
      .attr("width", x.bandwidth())
      .attr("height", (d) => y(0) - y(d.value))
      .attr("fill", (d) => d.color)
      .attr("opacity", (d) => state.selectedLabel && state.selectedLabel !== d.key ? 0.38 : 0.88)
      .attr("stroke", (d) => state.selectedLabel === d.key ? colors.ink : "none")
      .attr("stroke-width", 1.4)
      .on("click", (_, d) => setState({ selectedLabel: state.selectedLabel === d.key ? null : d.key }))
      .on("mousemove", (event, d) => tooltip(ui, event, `${d.label}<br>${d.value} rows`))
      .on("mouseleave", () => hideTooltip(ui));
  }

  function renderTimeline(svgEl, caseData, state, setState, ui) {
    const events = caseData.events || [];
    if (!events.length) {
      empty(svgEl, "Timeline unavailable: no trace rows or rolling strategy samples were found.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 420, 220);
    const margin = { top: 24, right: 16, bottom: 34, left: 78 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const maxDay = Math.max(caseData.level.deadline || 0, d3.max(events, (d) => d.day) || 0);
    const x = d3.scaleLinear().domain([0, Math.max(1, maxDay)]).range([margin.left, width - margin.right]);
    const lanes = ["Weather", "Action", "Resource"];
    const y = d3.scaleBand().domain(lanes).range([margin.top, height - margin.bottom]).padding(0.22);
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(Math.min(10, maxDay)).tickFormat((d) => `D${d}`).tickSizeOuter(0));
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).tickSizeOuter(0));

    const segmentWidth = Math.max(2, x(1) - x(0) - 1);
    svg.append("g")
      .selectAll("rect.weather")
      .data(events)
      .join("rect")
      .attr("class", "weather")
      .attr("x", (d) => x(d.day) - segmentWidth / 2)
      .attr("y", y("Weather"))
      .attr("width", segmentWidth)
      .attr("height", y.bandwidth())
      .attr("fill", (d) => weatherColor(d.weather))
      .attr("opacity", 0.82)
      .on("click", (_, d) => setState({ currentTime: d.day, selectedEvent: d.id, selectedLabel: d.action }))
      .on("mousemove", (event, d) => tooltip(ui, event, `Day ${d.day}<br>${d.weatherLabel}<br>${d.label}`))
      .on("mouseleave", () => hideTooltip(ui));

    svg.append("g")
      .selectAll("rect.action")
      .data(events)
      .join("rect")
      .attr("class", "action")
      .attr("x", (d) => x(d.day) - segmentWidth / 2)
      .attr("y", y("Action"))
      .attr("width", segmentWidth)
      .attr("height", y.bandwidth())
      .attr("fill", (d) => actionColor(d.action))
      .attr("opacity", (d) => state.selectedLabel && state.selectedLabel !== d.action ? 0.32 : 0.88)
      .attr("stroke", (d) => state.selectedEvent === d.id ? colors.ink : "none")
      .attr("stroke-width", 1.4)
      .on("click", (_, d) => setState({ currentTime: d.day, selectedEvent: d.id, selectedLabel: d.action }))
      .on("mousemove", (event, d) => tooltip(ui, event, [
        `Day ${d.day}`,
        `${d.label} / ${d.weatherLabel}`,
        `node ${d.node}`,
        d.evidence || "no extra evidence"
      ].join("<br>")))
      .on("mouseleave", () => hideTooltip(ui));

    const resourceY = d3.scaleLinear()
      .domain([0, d3.max(events, (d) => Math.max(d.water || 0, d.food || 0)) || 1])
      .range([y("Resource") + y.bandwidth(), y("Resource")]);
    const waterLine = d3.line().defined((d) => d.water !== null).x((d) => x(d.day)).y((d) => resourceY(d.water));
    const foodLine = d3.line().defined((d) => d.food !== null).x((d) => x(d.day)).y((d) => resourceY(d.food));
    svg.append("path")
      .datum(events)
      .attr("fill", "none")
      .attr("stroke", colors.blue)
      .attr("stroke-width", 1.8)
      .attr("d", waterLine);
    svg.append("path")
      .datum(events)
      .attr("fill", "none")
      .attr("stroke", colors.ok)
      .attr("stroke-width", 1.8)
      .attr("d", foodLine);

    const cursorX = x(Math.max(0, Math.min(maxDay, Number(state.currentTime || 0))));
    svg.append("line")
      .attr("x1", cursorX)
      .attr("x2", cursorX)
      .attr("y1", margin.top - 6)
      .attr("y2", height - margin.bottom)
      .attr("stroke", colors.ink)
      .attr("stroke-width", 1.2)
      .attr("stroke-dasharray", "4 4");
    svg.append("text")
      .attr("x", cursorX + 5)
      .attr("y", margin.top - 9)
      .attr("fill", colors.ink)
      .attr("font-size", 11)
      .text(`Day ${fmt(state.currentTime)}`);
  }

  function renderSpatial(svgEl, caseData, state, setState, ui) {
    const nodes = caseData.nodes || [];
    const edges = caseData.edges || [];
    if (!nodes.length || !edges.length) {
      empty(svgEl, "Spatial view unavailable: coordinate positions or adjacency edges are missing.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 400, 300);
    const margin = { top: 20, right: 20, bottom: 20, left: 20 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const xExtent = d3.extent(nodes, (d) => d.x);
    const yExtent = d3.extent(nodes, (d) => d.y);
    const x = d3.scaleLinear().domain(xExtent[0] === xExtent[1] ? [xExtent[0] - 1, xExtent[1] + 1] : xExtent).range([margin.left, width - margin.right]);
    const y = d3.scaleLinear().domain(yExtent[0] === yExtent[1] ? [yExtent[0] - 1, yExtent[1] + 1] : yExtent).range([height - margin.bottom, margin.top]);
    const byNode = new Map(nodes.map((node) => [node.node, node]));
    const meta = caseData.level;
    const currentEvent = selectedEvent(caseData, state);
    const currentNode = currentEvent ? currentEvent.node : null;
    const currentDay = Number(state.currentTime || 0);
    const pathEvents = (caseData.events || [])
      .filter((item) => item.day <= currentDay)
      .filter((item) => byNode.has(item.node))
      .sort((a, b) => a.day - b.day);
    const pathNodes = pathEvents.map((item) => item.node);
    const traversedEdges = new Set();
    pathEvents.forEach((item, index) => {
      const next = pathEvents[index + 1];
      if (!next || item.node === next.node) return;
      traversedEdges.add(`${item.node}->${next.node}`);
      traversedEdges.add(`${next.node}->${item.node}`);
    });
    const routeKeyNodes = new Set((caseData.routeKeyNodes || []).map((item) => item.node));
    if (currentNode !== null && currentNode !== undefined) routeKeyNodes.add(currentNode);
    const line = d3.line()
      .x((node) => x(byNode.get(node).x))
      .y((node) => y(byNode.get(node).y));

    const edgeGroup = svg.append("g");
    edges.filter((edge) => byNode.has(edge.source) && byNode.has(edge.target))
      .forEach((edge) => {
        const isPastPath = traversedEdges.has(`${edge.source}->${edge.target}`);
        edgeGroup.append("line")
          .attr("x1", x(byNode.get(edge.source).x))
          .attr("y1", y(byNode.get(edge.source).y))
          .attr("x2", x(byNode.get(edge.target).x))
          .attr("y2", y(byNode.get(edge.target).y))
          .attr("stroke", isPastPath ? colors.blueDark : "#dfe5ec")
          .attr("stroke-width", isPastPath ? 1.8 : 1)
          .attr("stroke-opacity", isPastPath ? 0.82 : 0.72)
          .attr("stroke-dasharray", isPastPath ? null : "4 4");
      });

    if (pathNodes.length > 1) {
      svg.append("path")
        .datum(pathNodes)
        .attr("fill", "none")
        .attr("stroke", colors.ink)
        .attr("stroke-width", 3)
        .attr("stroke-opacity", 0.78)
        .attr("stroke-linejoin", "round")
        .attr("stroke-linecap", "round")
        .attr("d", line);
    }

    function nodeRole(node) {
      if (node === meta.start_node) return "start";
      if (node === meta.goal_node) return "goal";
      if ((meta.mines || []).includes(node)) return "mine";
      if ((meta.villages || []).includes(node)) return "village";
      return "route";
    }

    function nodeFill(node, isCurrent) {
      if (isCurrent) return "#ffffff";
      const role = nodeRole(node);
      if (role === "start" || role === "village") return "#e8f2ea";
      if (role === "goal") return "#f6e7e4";
      if (role === "mine") return "#f7f0dc";
      return "#ffffff";
    }

    function nodeLabel(node) {
      const spec = (caseData.routeKeyNodes || []).find((item) => item.node === node);
      if (node === currentNode) return `current ${node}`;
      if (spec) return spec.label;
      return `node ${node}`;
    }

    const nodeGroup = svg.append("g");
    nodes.forEach((node) => {
      const isCurrent = node.node === currentNode;
      const isKey = routeKeyNodes.has(node.node);
      const radius = isCurrent ? 7.5 : isKey ? 6.5 : 4.5;

      if (isCurrent) {
        nodeGroup.append("circle")
          .attr("cx", x(node.x))
          .attr("cy", y(node.y))
          .attr("r", radius + 7)
          .attr("fill", "none")
          .attr("stroke", colors.blueDark)
          .attr("stroke-width", 2)
          .attr("opacity", 0.28);
      }

      nodeGroup.append("circle")
        .attr("cx", x(node.x))
        .attr("cy", y(node.y))
        .attr("r", radius)
        .attr("fill", nodeFill(node.node, isCurrent))
        .attr("stroke", isCurrent ? colors.ink : isKey ? colors.steel : "#9ca3af")
        .attr("stroke-width", isCurrent ? 2.4 : isKey ? 1.4 : 1)
        .attr("opacity", isKey || isCurrent ? 1 : 0.78)
        .style("cursor", "pointer")
        .on("click", () => {
          const match = caseData.events.find((item) => item.node === node.node);
          if (match) setState({ currentTime: match.day, selectedEvent: match.id, selectedTrack: node.node });
        })
        .on("mousemove", (event) => {
          const nodeEvents = caseData.events.filter((item) => item.node === node.node);
          const lastEvent = nodeEvents.filter((item) => item.day <= currentDay).at(-1) || nodeEvents[0];
          const action = lastEvent ? window.DesertVis.summarizeAction(lastEvent.action) : "--";
          const status = lastEvent ? (lastEvent.status || "--") : "--";
          const tooltipContent = `
            <strong>Node ${node.node}</strong><br>
            Role: ${nodeRole(node.node)}<br>
            Position: (${fmt(node.x, 1)}, ${fmt(node.y, 1)})<br>
            Day: ${lastEvent ? lastEvent.day : "--"}<br>
            Action: ${action}<br>
            Resource: W ${lastEvent ? fmt(lastEvent.water || 0, 0) : "--"} / F ${lastEvent ? fmt(lastEvent.food || 0, 0) : "--"}<br>
            Status: ${status}
          `;
          tooltip(ui, event, tooltipContent);
        })
        .on("mouseleave", () => hideTooltip(ui));
    });

    svg.append("g")
      .selectAll("text")
      .data(nodes.filter((node) => routeKeyNodes.has(node.node)))
      .join("text")
      .attr("x", (d) => Math.max(margin.left + 4, Math.min(width - margin.right - 4, x(d.x))))
      .attr("y", (d) => {
        const py = y(d.y);
        if (py < margin.top + 30) return py + 20;
        return py - (d.node === currentNode ? 16 : 11);
      })
      .attr("text-anchor", (d) => {
        const px = x(d.x);
        if (px < margin.left + 44) return "start";
        if (px > width - margin.right - 44) return "end";
        return "middle";
      })
      .attr("font-size", 10)
      .attr("font-weight", (d) => d.node === currentNode ? 760 : 680)
      .attr("fill", (d) => d.node === currentNode ? colors.ink : colors.muted)
      .text((d) => nodeLabel(d.node));
  }

  function renderProjection(svgEl, caseData, state, setState, ui) {
    const points = caseData.scenarioPoints || [];
    if (!points.length) {
      empty(svgEl, caseData.missing.embedding || "Projection view unavailable: no scenario or embedding rows were found.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 340, 300);
    const margin = { top: 24, right: 18, bottom: 42, left: 48 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const xExtent = d3.extent(points, (d) => d.stormCount);
    const yExtent = d3.extent(points, (d) => d.hotCount);
    const x = d3.scaleLinear().domain([Math.min(0, xExtent[0] - 0.5), xExtent[1] + 0.5]).nice().range([margin.left, width - margin.right]);
    const y = d3.scaleLinear().domain([Math.min(0, yExtent[0] - 0.5), yExtent[1] + 0.5]).nice().range([height - margin.bottom, margin.top]);
    const radius = d3.scaleSqrt().domain(d3.extent(points, (d) => d.arrivalDay) || [0, 1]).range([4, 8]);
    addGrid(svg, y, margin, width);
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(5).tickSizeOuter(0));
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(5).tickSizeOuter(0));
    svg.append("text")
      .attr("x", width / 2)
      .attr("y", height - 8)
      .attr("text-anchor", "middle")
      .attr("fill", colors.muted)
      .attr("font-size", 11)
      .text("storm count");
    svg.append("text")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2)
      .attr("y", 14)
      .attr("text-anchor", "middle")
      .attr("fill", colors.muted)
      .attr("font-size", 11)
      .text("hot-day count");

    const brushedIds = new Set(state.brushRange && state.brushRange.caseId === caseData.id ? state.brushRange.ids : []);
    svg.append("g")
      .selectAll("circle")
      .data(points)
      .join("circle")
      .attr("cx", (d) => x(d.stormCount))
      .attr("cy", (d) => y(d.hotCount))
      .attr("r", (d) => radius(d.arrivalDay || 0))
      .attr("fill", (d) => d.feasible ? colors.ok : colors.bad)
      .attr("opacity", (d) => brushedIds.size && !brushedIds.has(d.id) ? 0.24 : 0.82)
      .attr("stroke", (d) => state.selectedScenario === d.id ? colors.ink : "#ffffff")
      .attr("stroke-width", (d) => state.selectedScenario === d.id ? 2 : 1)
      .on("click", (_, d) => setState({ selectedScenario: d.id }))
      .on("mousemove", (event, d) => tooltip(ui, event, [
        `Scenario ${d.scenario}`,
        `${d.label} / ${d.status}`,
        `storm ${d.stormCount}, hot ${d.hotCount}`,
        `arrival day ${fmt(d.arrivalDay)}, objective ${fmt(d.objective, 1)}`
      ].join("<br>")))
      .on("mouseleave", () => hideTooltip(ui));

    const brush = d3.brush()
      .extent([[margin.left, margin.top], [width - margin.right, height - margin.bottom]])
      .on("end", (event) => {
        if (!event.selection) {
          setState({ brushRange: null });
          return;
        }
        const [[x0, y0], [x1, y1]] = event.selection;
        const ids = points
          .filter((point) => {
            const px = x(point.stormCount);
            const py = y(point.hotCount);
            return px >= x0 && px <= x1 && py >= y0 && py <= y1;
          })
          .map((point) => point.id);
        setState({ brushRange: { caseId: caseData.id, ids } });
      });
    svg.append("g").attr("class", "brush").call(brush);
  }

  function renderQuality(svgEl, caseData, state, setState, ui) {
    const items = caseData.qualityItems || [];
    if (!items.length) {
      empty(svgEl, "Quality view unavailable: no reliability, score, confidence, or solver status fields were found.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 330, 300);
    const margin = { top: 20, right: 16, bottom: 20, left: 136 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const y = d3.scaleBand().domain(items.map((d) => d.label)).range([margin.top, height - margin.bottom]).padding(0.26);
    const x = d3.scaleLinear().domain([0, 1]).range([margin.left, width - margin.right]);
    const score = (item) => item.status === "ok" ? 1 : item.status === "warn" ? 0.58 : 0.24;
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).tickSizeOuter(0));
    svg.append("g")
      .selectAll("rect")
      .data(items)
      .join("rect")
      .attr("x", margin.left)
      .attr("y", (d) => y(d.label))
      .attr("width", (d) => x(score(d)) - margin.left)
      .attr("height", y.bandwidth())
      .attr("fill", (d) => statusColor(d.status))
      .attr("opacity", 0.84)
      .on("click", (_, d) => {
        if (d.time !== null && d.time !== undefined) setState({ currentTime: d.time });
      })
      .on("mousemove", (event, d) => tooltip(ui, event, `${d.label}<br>${d.metric}<br>${d.explanation}`))
      .on("mouseleave", () => hideTooltip(ui));
    svg.append("g")
      .selectAll("text.metric")
      .data(items)
      .join("text")
      .attr("class", "metric")
      .attr("x", margin.left + 10)
      .attr("y", (d) => y(d.label) + y.bandwidth() / 2 + 4)
      .attr("fill", "#ffffff")
      .attr("font-size", 11)
      .attr("font-weight", 700)
      .text((d) => d.metric);
  }

  function cellColor(cell) {
    if (cell.kind === "action") return actionColor(cell.key);
    if (cell.kind === "weather") return weatherColor(cell.key);
    if (cell.kind === "resource") return statusColor(cell.status);
    if (cell.kind === "node") {
      if (cell.key === "start") return "#e8f2ea";
      if (cell.key === "goal") return "#f6e7e4";
      if (cell.key === "mine") return "#f7f0dc";
      if (cell.key === "village") return "#e7eef7";
      return "#f3f4f6";
    }
    return statusColor(cell.status);
  }

  function renderSequenceMatrix(svgEl, caseData, state, setState, ui) {
    const rows = caseData.derivedSequences || [];
    const cells = rows.flatMap((row) => row.cells.map((cell) => ({ ...cell, rowId: row.id, rowLabel: row.label })));
    if (!rows.length || !cells.length) {
      empty(svgEl, "Sequence matrix unavailable: no normalized event rows were found.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 560, 260);
    const margin = { top: 24, right: 18, bottom: 34, left: 96 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const maxDay = Math.max(caseData.level.deadline || 0, d3.max(cells, (d) => d.day) || 0);
    const x = d3.scaleLinear().domain([0, Math.max(1, maxDay)]).range([margin.left, width - margin.right]);
    const y = d3.scaleBand().domain(rows.map((row) => row.id)).range([margin.top, height - margin.bottom]).padding(0.2);
    const cellWidth = Math.max(3, x(1) - x(0) - 1);

    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).ticks(Math.min(12, maxDay)).tickFormat((d) => `D${d}`).tickSizeOuter(0));
    svg.append("g")
      .attr("class", "axis")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).tickFormat((id) => {
        const row = rows.find((item) => item.id === id);
        return row ? row.label : id;
      }).tickSizeOuter(0));

    const selectedIds = new Set(state.brushRange && state.brushRange.caseId === caseData.id && state.brushRange.ids ? state.brushRange.ids : []);
    svg.append("g")
      .selectAll("rect")
      .data(cells)
      .join("rect")
      .attr("x", (d) => x(d.day) - cellWidth / 2)
      .attr("y", (d) => y(d.rowId))
      .attr("width", cellWidth)
      .attr("height", y.bandwidth())
      .attr("fill", (d) => cellColor(d))
      .attr("stroke", (d) => state.selectedEvent === d.eventId ? colors.ink : "#ffffff")
      .attr("stroke-width", (d) => state.selectedEvent === d.eventId ? 1.6 : 0.7)
      .attr("opacity", (d) => {
        if (selectedIds.size && !selectedIds.has(d.eventId)) return 0.24;
        if (state.selectedLabel && d.kind === "action" && d.key !== state.selectedLabel) return 0.28;
        return 0.86;
      })
      .on("click", (_, d) => setState({
        currentTime: d.day,
        selectedEvent: d.eventId,
        selectedLabel: d.kind === "action" ? d.key : state.selectedLabel
      }))
      .on("mousemove", (event, d) => tooltip(ui, event, [
        `${d.rowLabel} / Day ${d.day}`,
        d.label,
        d.value,
        `status: ${d.status || "--"}`
      ].join("<br>")))
      .on("mouseleave", () => hideTooltip(ui));

    const current = Math.max(0, Math.min(maxDay, Number(state.currentTime || 0)));
    const cursorX = x(current);
    svg.append("line")
      .attr("x1", cursorX)
      .attr("x2", cursorX)
      .attr("y1", margin.top - 7)
      .attr("y2", height - margin.bottom)
      .attr("stroke", colors.ink)
      .attr("stroke-width", 1.1)
      .attr("stroke-dasharray", "4 4");
    svg.append("text")
      .attr("x", cursorX + 5)
      .attr("y", margin.top - 10)
      .attr("fill", colors.ink)
      .attr("font-size", 11)
      .text(`Day ${fmt(current)}`);

    const brush = d3.brushX()
      .extent([[margin.left, margin.top], [width - margin.right, height - margin.bottom]])
      .on("end", (event) => {
        if (!event.selection) {
          setState({ brushRange: null });
          return;
        }
        const [x0, x1] = event.selection;
        const timeRange = [Math.max(0, Math.floor(x.invert(x0))), Math.min(maxDay, Math.ceil(x.invert(x1)))];
        const ids = caseData.events
          .filter((item) => item.day >= timeRange[0] && item.day <= timeRange[1])
          .map((item) => item.id);
        setState({ brushRange: { caseId: caseData.id, timeRange, ids } });
      });
    const brushGroup = svg.append("g").attr("class", "brush").call(brush);

    function cellAtPointer(event) {
      const [px, py] = d3.pointer(event, svg.node());
      if (px < margin.left || px > width - margin.right || py < margin.top || py > height - margin.bottom) return null;
      const day = Math.max(0, Math.min(maxDay, Math.round(x.invert(px))));
      const rowId = rows.find((row) => {
        const rowY = y(row.id);
        return rowY !== undefined && py >= rowY && py <= rowY + y.bandwidth();
      })?.id;
      if (!rowId) return null;
      return cells.find((cell) => cell.rowId === rowId && cell.day === day) || null;
    }

    brushGroup.select(".overlay")
      .style("cursor", "crosshair")
      .on("click.forward", (event) => {
        if (event.defaultPrevented) return;
        const cell = cellAtPointer(event);
        if (!cell) return;
        setState({
          currentTime: cell.day,
          selectedEvent: cell.eventId,
          selectedLabel: cell.kind === "action" ? cell.key : state.selectedLabel
        });
      })
      .on("mousemove.forward", (event) => {
        const cell = cellAtPointer(event);
        if (!cell) {
          hideTooltip(ui);
          return;
        }
        tooltip(ui, event, [
          `${cell.rowLabel} / Day ${cell.day}`,
          cell.label,
          cell.value,
          `status: ${cell.status || "--"}`
        ].join("<br>"));
      })
      .on("mouseleave.forward", () => hideTooltip(ui));
  }

  function renderComparisonFlow(svgEl, caseData, state, setState, ui) {
    const flow = caseData.comparisonFlow || { links: [] };
    const links = flow.links || [];
    if (!links.length) {
      empty(svgEl, "Comparison flow unavailable: no scenario table or event transitions were found.");
      return;
    }

    clear(svgEl);
    const { width, height } = size(svgEl, 560, 260);
    const margin = { top: 30, right: 118, bottom: 20, left: 118 };
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    const available = height - margin.top - margin.bottom;
    const gap = 8;
    const total = d3.sum(links, (d) => d.value) || 1;
    const thickness = d3.scaleLinear().domain([0, total]).range([0, Math.max(1, available - gap * 2)]);

    function nodeLayout(keyAccessor) {
      const totals = d3.rollup(links, (items) => d3.sum(items, (item) => item.value), keyAccessor);
      let cursor = margin.top;
      return new Map(Array.from(totals, ([key, value]) => {
        const h = Math.max(12, thickness(value));
        const layout = { key, value, y0: cursor, y1: cursor + h };
        cursor += h + gap;
        return [key, layout];
      }));
    }

    const sourceNodes = nodeLayout((d) => d.source);
    const targetNodes = nodeLayout((d) => d.target);
    const sourceOffsets = new Map(Array.from(sourceNodes, ([key, node]) => [key, node.y0]));
    const targetOffsets = new Map(Array.from(targetNodes, ([key, node]) => [key, node.y0]));
    const sx = margin.left;
    const tx = width - margin.right;
    const nodeWidth = 12;

    svg.append("text")
      .attr("x", sx)
      .attr("y", 16)
      .attr("fill", colors.muted)
      .attr("font-size", 11)
      .attr("font-weight", 700)
      .text(flow.sourceTitle || "Source");
    svg.append("text")
      .attr("x", tx)
      .attr("y", 16)
      .attr("fill", colors.muted)
      .attr("font-size", 11)
      .attr("font-weight", 700)
      .text(flow.targetTitle || "Target");

    const band = d3.area()
      .x((d) => d.x)
      .y0((d) => d.y0)
      .y1((d) => d.y1)
      .curve(d3.curveBasis);

    svg.append("g")
      .attr("class", "flow-links")
      .selectAll("path")
      .data(links)
      .join("path")
      .attr("d", (d) => {
        const h = Math.max(2, thickness(d.value));
        const y0 = sourceOffsets.get(d.source) ?? margin.top;
        const y1 = targetOffsets.get(d.target) ?? margin.top;
        sourceOffsets.set(d.source, y0 + h);
        targetOffsets.set(d.target, y1 + h);
        const mid0 = sx + (tx - sx) * 0.42;
        const mid1 = sx + (tx - sx) * 0.58;
        return band([
          { x: sx + nodeWidth, y0, y1: y0 + h },
          { x: mid0, y0, y1: y0 + h },
          { x: mid1, y0: y1, y1: y1 + h },
          { x: tx, y0: y1, y1: y1 + h }
        ]);
      })
      .attr("fill", (d) => statusColor(d.status))
      .attr("opacity", (d) => {
        const selected = state.comparisonSelection;
        if (!selected || selected.caseId !== caseData.id) return 0.28;
        return selected.source === d.source && selected.target === d.target ? 0.52 : 0.12;
      })
      .attr("stroke", "none")
      .on("click", (_, d) => setState({
        comparisonSelection: { caseId: caseData.id, source: d.source, target: d.target },
        selectedLabel: flow.mode === "trace" ? d.sourceKey : state.selectedLabel,
        brushRange: d.ids ? { caseId: caseData.id, ids: d.ids } : state.brushRange
      }))
      .on("mousemove", (event, d) => tooltip(ui, event, [
        `${d.source} -> ${d.target}`,
        `${d.value} rows`,
        d.evidence || ""
      ].join("<br>")))
      .on("mouseleave", () => hideTooltip(ui));

    function drawNodes(nodes, x, anchor) {
      const group = svg.append("g");
      group.selectAll("rect")
        .data(Array.from(nodes.values()))
        .join("rect")
        .attr("x", x)
        .attr("y", (d) => d.y0)
        .attr("width", nodeWidth)
        .attr("height", (d) => Math.max(12, d.y1 - d.y0))
        .attr("fill", colors.steel)
        .attr("opacity", 0.82);
      group.selectAll("text")
        .data(Array.from(nodes.values()))
        .join("text")
        .attr("x", anchor === "start" ? x + nodeWidth + 6 : x - 6)
        .attr("y", (d) => (d.y0 + d.y1) / 2 + 4)
        .attr("text-anchor", anchor)
        .attr("fill", colors.ink)
        .attr("font-size", 11)
        .text((d) => `${d.key} (${fmt(d.value)})`);
    }

    drawNodes(sourceNodes, sx, "start");
    drawNodes(targetNodes, tx, "end");
  }

  window.DesertVis = window.DesertVis || {};
  window.DesertVis.colors = colors;
  window.DesertVis.renderDistribution = renderDistribution;
  window.DesertVis.renderTimeline = renderTimeline;
  window.DesertVis.renderSequenceMatrix = renderSequenceMatrix;
  window.DesertVis.renderComparisonFlow = renderComparisonFlow;
  window.DesertVis.renderSpatial = renderSpatial;
  window.DesertVis.renderProjection = renderProjection;
  window.DesertVis.renderQuality = renderQuality;
})();
