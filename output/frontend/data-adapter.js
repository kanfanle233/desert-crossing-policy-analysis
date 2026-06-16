(function () {
  "use strict";

  const ACTION_LABELS = {
    buy_start: "Initial Purchase",
    move: "Move",
    stay: "Stay",
    mine: "Mine"
  };

  const WEATHER_LABELS = {
    "晴朗": "Sunny",
    "高温": "Hot",
    "沙暴": "Storm",
    none: "Initial"
  };

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function asNumber(value, fallback = null) {
    if (value === null || value === undefined || value === "") return fallback;
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function relativePath(path) {
    if (!path || typeof path !== "string") return "--";
    const markers = ["/output/", "/configs/", "/desert_model/"];
    for (const marker of markers) {
      const idx = path.indexOf(marker);
      if (idx >= 0) return marker.slice(1) + path.slice(idx + marker.length);
    }
    return path.split("/").slice(-3).join("/");
  }

  function summarizeAction(action) {
    return ACTION_LABELS[action] || action || "Unknown";
  }

  function summarizeWeather(weather) {
    return WEATHER_LABELS[weather || "none"] || weather || "--";
  }

  function countBy(rows, key) {
    return rows.reduce((acc, row) => {
      const value = row[key] || "none";
      acc[value] = (acc[value] || 0) + 1;
      return acc;
    }, {});
  }

  function buildEdges(adjacency) {
    const edges = [];
    Object.entries(adjacency || {}).forEach(([source, targets]) => {
      asArray(targets).forEach((target) => {
        if (Number(target) > Number(source)) {
          edges.push({ source: Number(source), target: Number(target) });
        }
      });
    });
    return edges;
  }

  function normalizePositions(positions) {
    return Object.entries(positions || {}).map(([node, point]) => ({
      node: Number(node),
      x: asNumber(point && point.x, 0),
      y: asNumber(point && point.y, 0)
    }));
  }

  function normalizeTraceRows(rows, caseId) {
    return asArray(rows).map((row, index) => {
      const day = asNumber(row.day, index);
      const action = row.action || "unknown";
      const event = {
        id: `${caseId}:event:${index}`,
        caseId,
        index,
        day,
        time: day,
        start: Math.max(0, day - 0.45),
        end: day + 0.45,
        label: summarizeAction(action),
        action,
        weather: row.weather || "none",
        weatherLabel: summarizeWeather(row.weather),
        node: asNumber(row.node),
        fromNode: asNumber(row.from_node),
        toNode: asNumber(row.to_node),
        cash: asNumber(row.cash),
        water: asNumber(row.water),
        food: asNumber(row.food),
        consumeWater: asNumber(row.consume_water, 0),
        consumeFood: asNumber(row.consume_food, 0),
        buyWater: asNumber(row.buy_water, 0),
        buyFood: asNumber(row.buy_food, 0),
        income: asNumber(row.income, 0),
        finished: Boolean(row.finished),
        note: row.note || "",
        raw: row
      };
      event.evidence = [
        event.note,
        event.weather !== "none" ? `weather=${event.weather}` : "",
        event.income ? `income=${event.income}` : ""
      ].filter(Boolean).join("; ");
      return event;
    });
  }

  function normalizeRollingSteps(analysis, caseId) {
    const steps = analysis && analysis.rolling_strategy ? analysis.rolling_strategy.steps_sample : [];
    return normalizeTraceRows(asArray(steps).map((row) => ({
      ...row,
      from_node: row.node,
      to_node: row.node,
      weather: null,
      consume_water: null,
      consume_food: null,
      income: 0,
      note: "rolling strategy sample"
    })), caseId);
  }

  function computeTraceStats(events) {
    if (!events.length) {
      return {
        eventCount: 0,
        minWater: null,
        minFood: null,
        finalCash: null,
        arrivalDay: null,
        actionCounts: {}
      };
    }
    const final = events[events.length - 1];
    return {
      eventCount: events.length,
      minWater: d3.min(events, (d) => d.water),
      minFood: d3.min(events, (d) => d.food),
      finalCash: final.cash,
      arrivalDay: final.day,
      actionCounts: countBy(events, "action"),
      weatherCounts: countBy(events, "weather")
    };
  }

  function scenarioPoint(levelId, row) {
    const storm = asNumber(row.storm_count, 0);
    const hot = asNumber(row.hot_count, 0);
    const arrival = asNumber(row.arrival_day, 0);
    const objective = asNumber(row.objective, 0);
    return {
      id: `${levelId}:scenario:${row.scenario}`,
      caseId: String(levelId),
      scenario: asNumber(row.scenario),
      x: storm,
      y: hot,
      stormCount: storm,
      hotCount: hot,
      sunnyCount: asNumber(row.sunny_count, 0),
      feasible: Boolean(row.feasible),
      objective,
      arrivalDay: arrival,
      status: row.status || "--",
      label: Boolean(row.feasible) ? "Feasible" : "Infeasible",
      evidence: row.message || "",
      weather: row.weather || "",
      raw: row
    };
  }

  function transitionIssues(events, adjacency) {
    return events.slice(1).filter((event) => {
      const from = String(event.fromNode);
      const to = Number(event.toNode);
      return from !== String(to) && !asArray(adjacency && adjacency[from]).includes(to);
    });
  }

  function statusFromQuality(items) {
    if (items.some((item) => item.status === "bad")) return "bad";
    if (items.some((item) => item.status === "warn")) return "warn";
    return "ok";
  }

  function buildQualityItems(level, trace, events, analysis) {
    const items = [];
    const stats = computeTraceStats(events);
    const invalidTransitions = transitionIssues(events, level.adjacency || {});
    if (trace) {
      items.push({
        id: `${level.level_id}:solve`,
        label: "Solve status",
        metric: trace.status || "unknown",
        value: trace.feasible ? 1 : 0,
        status: trace.feasible ? "ok" : "bad",
        explanation: trace.message || "No solver message.",
        time: stats.arrivalDay
      });
      const metadata = trace.metadata || {};
      if (metadata.solver_engine || metadata.visited_states) {
        items.push({
          id: `${level.level_id}:solver-engine`,
          label: "Solver engine",
          metric: metadata.solver_engine || "recorded",
          value: asNumber(metadata.visited_states, 1),
          status: "ok",
          explanation: [
            metadata.solver_engine ? `engine=${metadata.solver_engine}` : "",
            metadata.visited_states ? `visited_states=${metadata.visited_states}` : "",
            metadata.purchase_step ? `purchase_step=${metadata.purchase_step}` : ""
          ].filter(Boolean).join("; ") || "Solver metadata is recorded in the trace.",
          time: stats.arrivalDay
        });
      }
    }
    if (events.length) {
      items.push({
        id: `${level.level_id}:resource`,
        label: "Resource margin",
        metric: `min W ${stats.minWater ?? "--"} / F ${stats.minFood ?? "--"}`,
        value: Math.min(stats.minWater ?? 0, stats.minFood ?? 0),
        status: (stats.minWater ?? 0) <= 0 || (stats.minFood ?? 0) <= 0 ? "warn" : "ok",
        explanation: "Yellow means the route reaches a boundary resource margin and should be interpreted as fragile, not incorrect.",
        time: stats.arrivalDay
      });
      items.push({
        id: `${level.level_id}:transition`,
        label: "Map transition validity",
        metric: `${invalidTransitions.length} invalid`,
        value: invalidTransitions.length,
        status: invalidTransitions.length ? "bad" : "ok",
        explanation: invalidTransitions.length ? "Red means at least one route step is not present in the adjacency table." : "Green means all non-stay movements are present in adjacency.",
        time: invalidTransitions[0] ? invalidTransitions[0].day : null
      });
    }
    if (analysis && analysis.scenario_count) {
      const failureRate = asNumber(analysis.failure_rate, 0);
      items.push({
        id: `${level.level_id}:scenario-reliability`,
        label: "Scenario reliability",
        metric: `${Math.round((1 - failureRate) * 100)}% feasible`,
        value: 1 - failureRate,
        status: failureRate > 0.2 ? "bad" : failureRate > 0 ? "warn" : "ok",
        explanation: "Green/Yellow/Red encodes feasible scenario coverage from sampled weather cases.",
        time: null
      });
    }
    if (analysis && analysis.cooperative_analysis) {
      const coop = analysis.cooperative_analysis;
      const failed = coop.feasible === false || coop.failure_rate === 1 || coop.feasible_count === 0;
      items.push({
        id: `${level.level_id}:cooperative`,
        label: "Cooperative feasibility",
        metric: failed ? "blocked" : "available",
        value: failed ? 0 : 1,
        status: failed ? "bad" : "ok",
        explanation: coop.failure_reason || "Cooperative analysis available from report summary.",
        time: null
      });
    }
    if (!items.length) {
      items.push({
        id: `${level.level_id}:missing-quality`,
        label: "Quality fields",
        metric: "missing",
        value: 0,
        status: "warn",
        explanation: "No confidence, ECE, Brier, uncertainty, or solver reliability fields were found for this case.",
        time: null
      });
    }
    return items;
  }

  function semanticBlocks(level, trace, analysis, extractedProblem) {
    const blocks = [];
    if (analysis && analysis.strategy) {
      blocks.push({
        id: `${level.level_id}:strategy`,
        label: "Strategy summary",
        text: analysis.strategy,
        time: null,
        kind: "analysis"
      });
    }
    asArray(analysis && analysis.notes).forEach((note, index) => {
      blocks.push({
        id: `${level.level_id}:note:${index}`,
        label: `Evidence note ${index + 1}`,
        text: note,
        time: null,
        kind: "note"
      });
    });
    if (analysis && analysis.deviation_analysis && analysis.deviation_analysis.note) {
      blocks.push({
        id: `${level.level_id}:deviation`,
        label: "Deviation analysis",
        text: analysis.deviation_analysis.note,
        time: null,
        kind: "analysis"
      });
    }
    if (trace && trace.message) {
      blocks.push({
        id: `${level.level_id}:solver`,
        label: "Solver evidence",
        text: trace.message,
        time: null,
        kind: "solver"
      });
    }
    const problemParagraphs = asArray(extractedProblem && extractedProblem.paragraphs);
    if (problemParagraphs.length) {
      blocks.push({
        id: `${level.level_id}:problem`,
        label: "Problem statement anchor",
        text: problemParagraphs.find((text) => text.includes(level.name)) || problemParagraphs[3] || problemParagraphs[0],
        time: null,
        kind: "source"
      });
    }
    if (!blocks.length) {
      blocks.push({
        id: `${level.level_id}:missing-transcript`,
        label: "Transcript not found",
        text: "No ASR, transcript, query, or timestamped text file was found in the local project.",
        time: null,
        kind: "empty"
      });
    }
    return blocks;
  }

  function resourceStatus(event) {
    const margin = Math.min(event.water ?? Infinity, event.food ?? Infinity);
    if (!Number.isFinite(margin)) return "warn";
    if (margin <= 0) return "bad";
    if (margin <= 20) return "warn";
    return "ok";
  }

  function nodeRole(level, node) {
    if (node === level.start_node) return "start";
    if (node === level.goal_node) return "goal";
    if (asArray(level.mines).includes(node)) return "mine";
    if (asArray(level.villages).includes(node)) return "village";
    return "route";
  }

  function statusFromItems(items) {
    return statusFromQuality(items.map((item) => ({ status: item })));
  }

  function buildTemplateRows(caseData) {
    const rows = [];
    const events = caseData.events || [];
    const scenarioPoints = caseData.scenarioPoints || [];
    const qualityItems = caseData.qualityItems || [];
    const totalEvents = Math.max(1, events.length);

    d3.rollups(events, (items) => items, (item) => item.action).forEach(([action, items]) => {
      const weatherCounts = d3.rollups(items, (group) => group.length, (item) => item.weather || "none");
      const resourceStates = items.map(resourceStatus);
      rows.push({
        id: `${caseData.id}:template:action:${action}`,
        label: summarizeAction(action),
        type: "action template",
        support: items.length,
        coverage: items.length / totalEvents,
        status: statusFromItems(resourceStates),
        metric: `${items.length} days`,
        fields: ["day", "action", "weather", "water", "food"],
        filter: { selectedLabel: action },
        evidence: `Action segment derived from ${items.length} trace rows.`,
        segments: weatherCounts.map(([weather, value]) => ({
          key: weather,
          label: summarizeWeather(weather),
          value,
          status: weather === "沙暴" ? "bad" : weather === "高温" ? "warn" : "ok"
        }))
      });
    });

    if (scenarioPoints.length) {
      const scenarioTotal = Math.max(1, scenarioPoints.length);
      d3.rollups(scenarioPoints, (items) => items, (item) => item.feasible ? "Feasible" : "Infeasible").forEach(([label, items]) => {
        rows.push({
          id: `${caseData.id}:template:scenario:${label}`,
          label: `${label} scenarios`,
          type: "scenario group",
          support: items.length,
          coverage: items.length / scenarioTotal,
          status: label === "Feasible" ? "ok" : "bad",
          metric: `${Math.round(items.length / scenarioTotal * 100)}%`,
          fields: ["scenario", "feasible", "storm_count", "hot_count", "objective"],
          filter: { selectedScenarioStatus: label },
          evidence: `Scenario table group from ${items.length} weather samples.`,
          segments: [
            { key: "storm", label: "storm", value: d3.sum(items, (item) => item.stormCount), status: "bad" },
            { key: "hot", label: "hot", value: d3.sum(items, (item) => item.hotCount), status: "warn" },
            { key: "sunny", label: "sunny", value: d3.sum(items, (item) => item.sunnyCount), status: "ok" }
          ].filter((segment) => segment.value > 0)
        });
      });
    }

    qualityItems.forEach((item) => {
      rows.push({
        id: `${caseData.id}:template:quality:${item.id}`,
        label: item.label,
        type: "quality signal",
        support: 1,
        coverage: 1 / Math.max(1, qualityItems.length),
        status: item.status,
        metric: item.metric,
        fields: ["qualityItems.status", "qualityItems.metric", "qualityItems.time"],
        filter: { selectedQuality: item.status },
        evidence: item.explanation,
        segments: [{ key: item.status, label: item.status, value: 1, status: item.status }]
      });
    });

    return rows.sort((a, b) => {
      const order = { bad: 0, warn: 1, ok: 2 };
      return (order[a.status] ?? 3) - (order[b.status] ?? 3) || b.support - a.support;
    });
  }

  function buildDerivedSequences(caseData) {
    const events = caseData.events || [];
    if (!events.length) return [];
    const makeCells = (kind, mapper) => events.map((event) => ({
      id: `${event.id}:${kind}`,
      eventId: event.id,
      day: event.day,
      time: event.day,
      kind,
      ...mapper(event)
    }));
    return [
      {
        id: "weather",
        label: "Weather",
        fields: ["day", "weather"],
        cells: makeCells("weather", (event) => ({
          key: event.weather || "none",
          label: event.weatherLabel,
          value: event.weatherLabel,
          status: event.weather === "沙暴" ? "bad" : event.weather === "高温" ? "warn" : "ok"
        }))
      },
      {
        id: "action",
        label: "Action",
        fields: ["day", "action"],
        cells: makeCells("action", (event) => ({
          key: event.action,
          label: event.label,
          value: event.label,
          status: resourceStatus(event)
        }))
      },
      {
        id: "resource",
        label: "Resource",
        fields: ["day", "water", "food"],
        cells: makeCells("resource", (event) => {
          const status = resourceStatus(event);
          return {
            key: status,
            label: status === "ok" ? "stable margin" : status === "warn" ? "fragile margin" : "boundary margin",
            value: `W ${event.water ?? "--"} / F ${event.food ?? "--"}`,
            status
          };
        })
      },
      {
        id: "node",
        label: "Node Role",
        fields: ["node", "from_node", "to_node"],
        cells: makeCells("node", (event) => ({
          key: nodeRole(caseData.level, event.node),
          label: `node ${event.node}`,
          value: nodeRole(caseData.level, event.node),
          status: event.finished ? "ok" : "warn"
        }))
      }
    ];
  }

  function scenarioPressure(point) {
    const pairs = [
      ["Storm-heavy", point.stormCount],
      ["Hot-heavy", point.hotCount],
      ["Sunny-heavy", point.sunnyCount]
    ].sort((a, b) => b[1] - a[1]);
    return pairs[0][1] ? pairs[0][0] : "Balanced";
  }

  function buildComparisonFlow(caseData) {
    const scenarioPoints = caseData.scenarioPoints || [];
    const events = caseData.events || [];
    if (scenarioPoints.length) {
      const grouped = d3.rollups(
        scenarioPoints,
        (items) => items,
        (point) => scenarioPressure(point),
        (point) => point.feasible ? "Feasible" : "Infeasible"
      );
      const links = [];
      grouped.forEach(([source, targets]) => {
        targets.forEach(([target, items]) => {
          links.push({
            source,
            target,
            value: items.length,
            sourceKey: source,
            targetKey: target,
            status: target === "Feasible" ? "ok" : "bad",
            ids: items.map((item) => item.id),
            evidence: `${items.length} scenarios: ${source} -> ${target}`
          });
        });
      });
      return {
        mode: "scenario",
        sourceTitle: "Weather Template",
        targetTitle: "Scenario Outcome",
        links
      };
    }

    const grouped = d3.rollups(
      events,
      (items) => items,
      (event) => event.action || "unknown",
      (event) => event.weather || "none"
    );
    const links = [];
    grouped.forEach(([source, targets]) => {
      targets.forEach(([target, items]) => {
        links.push({
          source: summarizeAction(source),
          target: summarizeWeather(target),
          value: items.length,
          sourceKey: source,
          targetKey: target,
          status: target === "沙暴" ? "bad" : target === "高温" ? "warn" : "ok",
          ids: items.map((item) => item.id),
          evidence: `${items.length} trace rows: ${summarizeAction(source)} -> ${summarizeWeather(target)}`
        });
      });
    });
    return {
      mode: "trace",
      sourceTitle: "Action Template",
      targetTitle: "Weather Context",
      links
    };
  }

  function buildViewSpecs(caseData) {
    const hasEvents = caseData.events.length > 0;
    const hasMap = caseData.nodes.length > 0 && caseData.edges.length > 0;
    const hasScenario = caseData.scenarioPoints.length > 0;
    const hasQuality = caseData.qualityItems.length > 0;
    return [
      {
        id: "timeline",
        title: "Linked Timeline",
        type: "temporal",
        available: hasEvents,
        marks: ["rect", "line", "cursor"],
        encodings: ["x: day", "color: action/weather", "y: lane"],
        interactions: ["seek", "hover", "label filter"],
        sourceFields: ["trace.rows.day", "trace.rows.action", "trace.rows.weather"],
        note: hasEvents ? "Trace rows are treated as event segments." : "No timestamped trace rows available."
      },
      {
        id: "sequenceMatrix",
        title: "Sequence Matrix",
        type: "matrix",
        available: hasEvents,
        marks: ["cell"],
        encodings: ["column: day", "row: semantic lane", "fill: event state"],
        interactions: ["click seek", "brush time range", "hover evidence"],
        sourceFields: ["day", "action", "weather", "node", "water", "food"],
        note: "VideoPro-style compact event matrix built from normalized trace rows."
      },
      {
        id: "comparisonFlow",
        title: "Comparison Flow",
        type: "alluvial",
        available: caseData.comparisonFlow.links.length > 0,
        marks: ["band", "node"],
        encodings: ["width: support", "color: reliability status"],
        interactions: ["hover support", "click linked selection"],
        sourceFields: hasScenario ? ["scenario.weather", "scenario.feasible"] : ["action", "weather"],
        note: hasScenario ? "Scenario table is mapped to weather pressure -> feasibility." : "Trace rows are mapped to action -> weather."
      },
      {
        id: "spatial",
        title: "Spatial Route",
        type: "node-link map",
        available: hasMap,
        marks: ["line", "circle", "path"],
        encodings: ["x/y: map coordinates", "stroke: route", "shape: node role"],
        interactions: ["click node seek", "current-time highlight"],
        sourceFields: ["positions.x", "positions.y", "adjacency", "trace.rows.node"],
        note: hasMap ? "Uses local map geometry and adjacency." : caseData.missing.embedding
      },
      {
        id: "projection",
        title: "Projection / Cluster",
        type: "scatter",
        available: hasScenario,
        marks: ["point", "brush"],
        encodings: ["x: storm_count", "y: hot_count", "color: feasible", "size: arrival_day"],
        interactions: ["brush", "hover", "scenario select"],
        sourceFields: ["storm_count", "hot_count", "feasible", "arrival_day"],
        note: hasScenario ? "Scenario table substitutes for missing UMAP/t-SNE embeddings." : caseData.missing.embedding
      },
      {
        id: "quality",
        title: "Quality / Reliability",
        type: "status bars",
        available: hasQuality,
        marks: ["bar", "label"],
        encodings: ["length: trust score", "color: Green/Yellow/Red status"],
        interactions: ["click issue seek", "hover explanation"],
        sourceFields: ["qualityItems.status", "qualityItems.metric", "qualityItems.explanation"],
        note: "Solver validity, resource margin, scenario reliability, and cooperative checks are used as reliability signals."
      },
      {
        id: "semantic",
        title: "Semantic Evidence",
        type: "text stream",
        available: caseData.semanticBlocks.length > 0,
        marks: ["text row"],
        encodings: ["order: evidence stream", "highlight: current time"],
        interactions: ["click evidence", "linked detail"],
        sourceFields: ["analysis.strategy", "analysis.notes", "problem_summary.paragraphs"],
        note: caseData.missing.transcript
      },
      {
        id: "video",
        title: "Video Player",
        type: "media",
        available: false,
        marks: ["empty state"],
        encodings: ["currentTime: timeline cursor"],
        interactions: ["seek placeholder"],
        sourceFields: [],
        note: caseData.missing.video
      }
    ];
  }

  function buildKpiItems(caseData) {
    const objective = caseData.stats.objective;
    const actionCounts = caseData.stats.actionCounts || {};
    const actionSummary = Object.entries(actionCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([action, count]) => `${summarizeAction(action)} ${count}`)
      .join(" / ");
    return [
      { id: "duration", label: "Duration", value: `${caseData.level.deadline ?? "--"} days`, tone: "neutral" },
      { id: "players", label: "Players", value: `${caseData.level.players || 1}`, tone: "neutral" },
      { id: "events", label: "Events", value: `${caseData.stats.eventCount}`, tone: "neutral" },
      { id: "objective", label: "Objective", value: objective === null || objective === undefined ? "--" : objective, tone: "neutral", digits: 1 },
      { id: "actions", label: "Action Mix", value: actionSummary || "no events", tone: "neutral" },
      { id: "quality", label: "Reliability", value: caseData.qualityStatus, tone: caseData.qualityStatus }
    ];
  }

  function buildRouteKeyNodes(level, currentNode) {
    const keyed = new Map();
    function add(node, label, role) {
      if (node === null || node === undefined) return;
      keyed.set(node, { node, label, role });
    }
    add(level.start_node, `start ${level.start_node}`, "start");
    add(level.goal_node, `goal ${level.goal_node}`, "goal");
    asArray(level.mines).forEach((node) => add(node, `mine ${node}`, "mine"));
    asArray(level.villages).forEach((node) => add(node, `village ${node}`, "village"));
    add(currentNode, `current ${currentNode}`, "current");
    return Array.from(keyed.values());
  }

  function buildQualitySummary(items) {
    const counts = countBy(items, "status");
    const primary = items.find((item) => item.status === "bad")
      || items.find((item) => item.status === "warn")
      || items[0]
      || null;
    return {
      status: statusFromQuality(items),
      counts,
      primaryLabel: primary ? primary.label : "Quality fields",
      primaryReason: primary ? primary.explanation : "No reliability fields were found.",
      missingConfidence: true
    };
  }

  function normalize(raw) {
    const levels = raw && raw.levels ? raw.levels : {};
    const traces = raw && raw.traces ? raw.traces : {};
    const analysisList = asArray(raw && raw.analysis_summary);
    const analysisByLevel = new Map(analysisList.map((item) => [String(item.level_id), item]));
    const scenarioTables = raw && raw.scenario_tables ? raw.scenario_tables : {};
    const extractedProblem = raw && raw.extracted_problem ? raw.extracted_problem : null;
    const cases = Object.values(levels).map((level) => {
      const id = String(level.level_id);
      const trace = traces[id] || null;
      const analysis = analysisByLevel.get(id) || null;
      const events = trace ? normalizeTraceRows(trace.rows, id) : normalizeRollingSteps(analysis, id);
      const scenarioPoints = asArray(scenarioTables[id]).map((row) => scenarioPoint(id, row));
      const nodes = normalizePositions(level.positions);
      const edges = buildEdges(level.adjacency);
      const stats = {
        ...computeTraceStats(events),
        objective: trace ? trace.objective_value : analysis ? analysis.single_player_objective || analysis.best_objective : null,
        feasible: trace ? Boolean(trace.feasible) : analysis ? analysis.failure_rate === 0 : null,
        scenarioCount: analysis ? asNumber(analysis.scenario_count, 0) : scenarioPoints.length,
        feasibleScenarios: analysis ? asNumber(analysis.feasible_scenarios, 0) : scenarioPoints.filter((d) => d.feasible).length,
        failureRate: analysis ? asNumber(analysis.failure_rate, null) : null
      };
      const qualityItems = buildQualityItems(level, trace, events, analysis);
      const caseData = {
        id,
        label: `${level.name || `Level ${id}`} / Level ${id}`,
        level,
        trace,
        analysis,
        events,
        nodes,
        edges,
        path: events.map((event) => event.node).filter((node) => node !== null && node !== undefined),
        scenarioPoints,
        semanticBlocks: semanticBlocks(level, trace, analysis, extractedProblem),
        qualityItems,
        qualityStatus: statusFromQuality(qualityItems),
        stats,
        missing: {
          video: "No .mp4/.mov/.webm files or video_path fields were found.",
          transcript: "No transcript/asr/text alignment file with timestamps was found.",
          embedding: scenarioPoints.length ? "" : "No UMAP/t-SNE/PCA/embedding file was found; scenario table is used only when available.",
          confidence: "No ECE/Brier/uncertainty fields were found; solver and scenario reliability are used instead."
        }
      };
      caseData.templateRows = buildTemplateRows(caseData);
      caseData.derivedSequences = buildDerivedSequences(caseData);
      caseData.comparisonFlow = buildComparisonFlow(caseData);
      caseData.viewSpecs = buildViewSpecs(caseData);
      caseData.viewAvailability = caseData.viewSpecs.reduce((acc, spec) => {
        acc[spec.id] = Boolean(spec.available);
        return acc;
      }, {});
      caseData.kpiItems = buildKpiItems(caseData);
      caseData.routeKeyNodes = buildRouteKeyNodes(level, caseData.events[0] ? caseData.events[0].node : null);
      caseData.qualitySummary = buildQualitySummary(qualityItems);
      return caseData;
    });

    const sourceRows = Object.entries(raw.sources || {}).map(([key, source]) => ({
      key,
      path: relativePath(source.path),
      exists: Boolean(source.exists),
      bytes: source.bytes || 0,
      modified: source.modified || "--"
    }));

    const schema = {
      time: ["day"],
      category: ["action", "weather", "status", "feasible"],
      coordinate: ["positions.x", "positions.y", "node", "from_node", "to_node"],
      quality: ["feasible", "status", "failure_rate", "min_water", "min_food"],
      trajectory: ["trace.rows", "rolling_strategy.steps_sample"],
      projection: ["scenario_tables.storm_count", "scenario_tables.hot_count"],
      video: []
    };

    return {
      generatedAt: raw.generated_at || raw.generated || "--",
      cases,
      caseMap: new Map(cases.map((item) => [item.id, item])),
      sourceRows,
      schema,
      raw
    };
  }

  window.DesertVis = window.DesertVis || {};
  window.DesertVis.normalize = normalize;
  window.DesertVis.formatNumber = function formatNumber(value, digits = 0) {
    if (value === null || value === undefined || value === "") return "--";
    if (typeof value === "number") {
      return value.toLocaleString("en-US", { maximumFractionDigits: digits });
    }
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("en-US", { maximumFractionDigits: digits }) : String(value);
  };
  window.DesertVis.summarizeAction = summarizeAction;
  window.DesertVis.summarizeWeather = summarizeWeather;
})();
