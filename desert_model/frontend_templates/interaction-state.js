(function () {
  "use strict";

  function createInteractionState(initialState) {
    let state = { ...initialState };
    const listeners = new Set();

    function getState() {
      return { ...state };
    }

    function setState(patch) {
      const next = typeof patch === "function" ? patch(state) : patch;
      state = { ...state, ...next };
      listeners.forEach((listener) => listener(getState()));
    }

    function subscribe(listener) {
      listeners.add(listener);
      return function unsubscribe() {
        listeners.delete(listener);
      };
    }

    return { getState, setState, subscribe };
  }

  window.DesertVis = window.DesertVis || {};
  window.DesertVis.createInteractionState = createInteractionState;
})();
