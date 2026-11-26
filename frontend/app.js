const state = {
  token: null,
  user: null,
  organizations: [],
  organizationId: null,
  computes: [],
  cursor: null,
  operations: [],
  activeView: "overview",
  refreshing: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const opStorageKey = "kubo-dashboard-operation-ids";
let toastTimer;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[character]);
}

function initials(value) {
  const first = String(value || "K").trim().charAt(0);
  return first ? first.toUpperCase() : "K";
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function statusClass(value) {
  const normalized = String(value || "unknown").toLowerCase();
  return [
    "running", "succeeded", "stopped", "failed", "terminated",
    "accepted", "pending", "requested", "provisioning", "starting",
    "stopping", "terminating",
  ].includes(normalized) ? `status-${normalized}` : "status-unknown";
}

function statusPill(value) {
  const label = String(value || "unknown").replaceAll("_", " ");
  return `<span class="status-pill ${statusClass(value)}"><span class="status-dot"></span>${escapeHtml(label)}</span>`;
}

async function request(service, path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response;
  try {
    response = await fetch(`/api/${service}${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new Error(`${service === "iam" ? "IAM" : "Compute"} API could not be reached. Check that the backend is running.`);
  }

  const responseText = await response.text();
  let body = null;
  if (responseText) {
    try {
      body = JSON.parse(responseText);
    } catch {
      body = { detail: responseText };
    }
  }
  if (!response.ok) {
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((entry) => entry.msg).join("; ")
      : body?.detail;
    throw new Error(detail || `Request failed with status ${response.status}.`);
  }
  return body;
}

function api(service, path, method = "GET", body, extraHeaders = {}) {
  const options = { method, headers: extraHeaders };
  if (body !== undefined) options.body = JSON.stringify(body);
  return request(service, path, options);
}

function showToast(message, kind = "error") {
  const region = $("#toast-region");
  const toast = document.createElement("div");
  toast.className = `toast ${kind === "success" ? "success" : ""}`;
  toast.textContent = message;
  region.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function setInlineError(selector, message) {
  const element = $(selector);
  element.textContent = message;
  element.hidden = !message;
}

function setHealth(service, healthy) {
  const element = $(`#${service}-health`);
  element.className = `status-pill ${healthy ? "status-healthy" : "status-unhealthy"}`;
  element.innerHTML = `<span class="status-dot"></span>${healthy ? "Operational" : "Unavailable"}`;
}

async function checkHealth() {
  const results = await Promise.all([
    api("iam", "/health/ready").then(() => true).catch(() => false),
    api("compute", "/health/ready").then(() => true).catch(() => false),
  ]);
  setHealth("iam", results[0]);
  setHealth("compute", results[1]);
  const onlineCount = results.filter(Boolean).length;
  const label = $("#connection-label");
  label.textContent = onlineCount === 2 ? "All services operational" : `${onlineCount} of 2 services online`;
  label.parentElement.classList.toggle("offline", onlineCount !== 2);
}

function storedOperationIds() {
  try {
    const value = JSON.parse(sessionStorage.getItem(opStorageKey) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function saveOperationIds() {
  sessionStorage.setItem(opStorageKey, JSON.stringify(state.operations.slice(0, 40)));
}

function rememberOperation(operation, compute) {
  const existing = storedOperationIds().filter((item) => item.id !== operation.id);
  existing.unshift({
    id: operation.id,
    computeId: operation.compute_id || compute?.id || "",
    computeName: compute?.name || "Compute resource",
    action: operation.action,
    organizationId: state.organizationId,
    createdAt: operation.created_at || new Date().toISOString(),
  });
  state.operations = existing.slice(0, 40);
  saveOperationIds();
  renderActivity();
}

async function refreshOperationStatuses() {
  if (!state.token || !state.organizationId || state.operations.length === 0) return;
  const sameOrg = state.operations.filter((item) => item.organizationId === state.organizationId);
  const refreshed = await Promise.all(sameOrg.map(async (item) => {
    try {
      const operation = await api(
        "compute",
        `/api/v1/organizations/${encodeURIComponent(item.organizationId)}/operations/${encodeURIComponent(item.id)}`,
      );
      return { ...item, ...operation, computeName: item.computeName };
    } catch {
      return item;
    }
  }));
  const byId = new Map(refreshed.map((item) => [item.id, item]));
  state.operations = state.operations.map((item) => byId.get(item.id) || item);
  saveOperationIds();
  renderActivity();
}

async function loadOrganizations() {
  state.organizations = await api("iam", "/api/v1/organizations");
  const selectedExists = state.organizations.some((organization) => organization.id === state.organizationId);
  if (!selectedExists) state.organizationId = state.organizations[0]?.id || null;
  renderOrganizations();
  if (state.organizations.length === 0) {
    $("#organization-dialog").showModal();
  } else {
    await loadComputes();
  }
}

function renderOrganizations() {
  const select = $("#organization-select");
  select.innerHTML = state.organizations.map((organization) =>
    `<option value="${escapeHtml(organization.id)}">${escapeHtml(organization.name)}</option>`
  ).join("");
  select.value = state.organizationId || "";
  $("#organization-count").textContent = String(state.organizations.length);
  $("#organization-list").innerHTML = state.organizations.length
    ? state.organizations.map((organization) => `
      <button class="organization-item ${organization.id === state.organizationId ? "selected" : ""}" data-select-org="${escapeHtml(organization.id)}">
        <span class="org-icon">⌂</span>
        <span class="org-info"><strong>${escapeHtml(organization.name)}</strong><small>${escapeHtml(organization.id)}</small></span>
        <span class="role-badge">${escapeHtml(organization.role)}</span>
      </button>
    `).join("")
    : `<div class="activity-empty">No organizations yet. Create one to begin.</div>`;
}

async function loadComputes(append = false) {
  if (!state.token || !state.organizationId) {
    state.computes = [];
    renderComputes();
    return;
  }
  const params = new URLSearchParams({ limit: "50" });
  if (append && state.cursor) params.set("cursor", state.cursor);
  const result = await api(
    "compute",
    `/api/v1/organizations/${encodeURIComponent(state.organizationId)}/computes?${params}`,
  );
  state.computes = append ? [...state.computes, ...result.items] : result.items;
  state.cursor = result.next_cursor;
  renderComputes();
}

function renderComputes() {
  const search = ($("#compute-search")?.value || "").trim().toLowerCase();
  const filtered = state.computes.filter((compute) =>
    `${compute.name} ${compute.image} ${compute.profile}`.toLowerCase().includes(search)
  );
  $("#compute-result-count").textContent = `${filtered.length} resource${filtered.length === 1 ? "" : "s"}`;
  $("#nav-compute-count").textContent = String(state.computes.length);
  $("#stat-total").textContent = String(state.computes.length);
  $("#stat-running").textContent = String(state.computes.filter((item) => item.observed_state === "running").length);
  $("#stat-pending").textContent = String(state.computes.filter((item) =>
    ["requested", "provisioning", "starting", "stopping", "terminating"].includes(item.observed_state)
  ).length);
  $("#stat-failed").textContent = String(state.computes.filter((item) => item.observed_state === "failed").length);

  const tableRows = (items, overview = false) => items.map((compute) => {
    const stateName = compute.observed_state;
    const transitional = ["requested", "provisioning", "starting", "stopping", "terminating"].includes(stateName);
    const actions = [];
    if (stateName === "running") actions.push(`<button class="mini-button" data-resource-action="stop" data-resource-id="${escapeHtml(compute.id)}">Stop</button>`);
    if (stateName === "stopped") actions.push(`<button class="mini-button" data-resource-action="start" data-resource-id="${escapeHtml(compute.id)}">Start</button>`);
    if (!["terminated", "terminating"].includes(stateName)) {
      actions.push(`<button class="mini-button danger" data-resource-action="delete" data-resource-id="${escapeHtml(compute.id)}">Delete</button>`);
    }
    if (overview) {
      return `<tr>
        <td><div class="resource-cell"><span class="resource-icon">▦</span><div><div class="resource-name">${escapeHtml(compute.name)}</div><div class="resource-id">${escapeHtml(compute.id.slice(0, 8))}</div></div></div></td>
        <td class="mono-cell">${escapeHtml(compute.image)}</td>
        <td>${escapeHtml(compute.profile)}</td>
        <td>${statusPill(stateName)}</td>
        <td>${escapeHtml(formatDate(compute.created_at))}</td>
        <td><button class="mini-button" data-resource-details="${escapeHtml(compute.id)}">Details</button></td>
      </tr>`;
    }
    if (transitional) actions.unshift(`<button class="mini-button" disabled>Working</button>`);
    return `<tr>
      <td><div class="resource-cell"><span class="resource-icon">▦</span><div><div class="resource-name">${escapeHtml(compute.name)}</div><div class="resource-id">${escapeHtml(compute.id.slice(0, 8))}</div></div></div></td>
      <td class="mono-cell">${escapeHtml(compute.image)}</td>
      <td>${escapeHtml(compute.profile)}</td>
      <td>${statusPill(stateName)}</td>
      <td>${escapeHtml(formatDate(compute.updated_at))}</td>
      <td><div class="row-actions">${actions.join("")}<button class="mini-button" data-resource-details="${escapeHtml(compute.id)}">View</button></div></td>
    </tr>`;
  }).join("");

  const overviewRows = $("#overview-compute-rows");
  overviewRows.innerHTML = tableRows(state.computes.slice(0, 5), true);
  $("#overview-empty").hidden = state.computes.length !== 0;
  $("#overview-compute-rows").closest("table").hidden = state.computes.length === 0;

  $("#compute-rows").innerHTML = tableRows(filtered);
  const empty = $("#compute-empty");
  empty.hidden = filtered.length !== 0;
  $("#compute-rows").closest("table").hidden = filtered.length === 0;
  $("#load-more").hidden = !state.cursor;
}

async function refreshDashboard(silent = false) {
  if (!state.token || state.refreshing) return;
  state.refreshing = true;
  $("#refresh-button").classList.add("spinning");
  try {
    await Promise.all([checkHealth(), loadComputes(), refreshOperationStatuses()]);
  } catch (error) {
    if (!silent) showToast(error.message);
  } finally {
    state.refreshing = false;
    $("#refresh-button").classList.remove("spinning");
  }
}

function renderActivity() {
  const active = state.operations.filter((item) => item.organizationId === state.organizationId);
  const html = active.length ? active.slice(0, 8).map((operation) => `
    <article class="activity-item">
      <span class="activity-marker">${escapeHtml(String(operation.action || "op").charAt(0).toUpperCase())}</span>
      <div class="activity-copy">
        <div class="activity-title">
          <span>${escapeHtml(operation.action || "operation")} · ${escapeHtml(operation.computeName || "Compute resource")}</span>
          ${statusPill(operation.status || "accepted")}
          <span class="activity-time">${escapeHtml(formatDate(operation.updated_at || operation.createdAt))}</span>
        </div>
        <div class="activity-subtitle">${operation.last_error_message
          ? escapeHtml(operation.last_error_message)
          : `Operation ${escapeHtml(String(operation.id || "").slice(0, 8))} · ${escapeHtml(operation.compute_id || operation.computeId || "resource pending")}`}</div>
      </div>
    </article>
  `).join("") : `<div class="activity-empty">No operations tracked in this browser yet. Create or change a compute resource to see activity.</div>`;
  $("#activity-list").innerHTML = html;
  $("#overview-activity").innerHTML = active.length
    ? active.slice(0, 3).map((operation) => `
      <article class="activity-item">
        <span class="activity-marker">${escapeHtml(String(operation.action || "op").charAt(0).toUpperCase())}</span>
        <div class="activity-copy">
          <div class="activity-title"><span>${escapeHtml(operation.action || "operation")} · ${escapeHtml(operation.computeName || "Compute resource")}</span>${statusPill(operation.status || "accepted")}</div>
          <div class="activity-subtitle">${escapeHtml(operation.last_error_message || `Operation ${String(operation.id || "").slice(0, 8)}`)}</div>
        </div>
        <span class="activity-time">${escapeHtml(formatDate(operation.updated_at || operation.createdAt))}</span>
      </article>
    `).join("")
    : `<div class="activity-empty">New resource operations will appear here.</div>`;
}

function setActiveView(viewName) {
  const knownViews = ["overview", "compute", "identity", "activity"];
  if (!knownViews.includes(viewName)) return;
  state.activeView = viewName;
  $$(".view").forEach((view) => {
    const active = view.id === `view-${viewName}`;
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === viewName));
  const labels = { overview: "Overview", compute: "Compute", identity: "Identity & access", activity: "Activity" };
  $("#breadcrumb-view").textContent = labels[viewName];
}

function showDashboard() {
  $("#auth-screen").hidden = true;
  $("#app-shell").hidden = false;
  const displayName = state.user?.email?.split("@")[0] || "Kubo user";
  $("#user-name").textContent = displayName;
  $("#user-email").textContent = state.user?.email || "";
  $("#top-avatar").textContent = initials(displayName);
  $("#user-avatar").textContent = initials(displayName);
  $("#identity-avatar").textContent = initials(displayName);
  $("#identity-name").textContent = displayName;
  $("#identity-email").textContent = state.user?.email || "";
  $("#greeting-heading").textContent = `Welcome back, ${displayName}.`;
  setActiveView("overview");
}

function showLogin() {
  state.token = null;
  state.user = null;
  state.organizations = [];
  state.organizationId = null;
  state.computes = [];
  state.operations = [];
  sessionStorage.removeItem(opStorageKey);
  $("#app-shell").hidden = true;
  $("#auth-screen").hidden = false;
  $("#login-password").value = "";
}

async function signIn(event) {
  event.preventDefault();
  const button = $("#login-form button[type=submit]");
  const formData = new FormData(event.currentTarget);
  setInlineError("#login-error", "");
  button.disabled = true;
  try {
    const result = await api("iam", "/api/v1/auth/login", "POST", {
      email: formData.get("email"),
      password: formData.get("password"),
    });
    state.token = result.access_token;
    state.user = await api("iam", "/api/v1/users/me");
    state.operations = storedOperationIds();
    showDashboard();
    await loadOrganizations();
    await checkHealth();
    await refreshOperationStatuses();
    showToast("Signed in successfully.", "success");
  } catch (error) {
    state.token = null;
    setInlineError("#login-error", error.message);
  } finally {
    button.disabled = false;
  }
}

async function submitCompute(event) {
  event.preventDefault();
  if (!state.organizationId) {
    showToast("Create or select an organization first.");
    return;
  }
  const form = event.currentTarget;
  const submit = $("#create-compute-submit");
  const data = new FormData(form);
  setInlineError("#compute-form-error", "");
  submit.disabled = true;
  try {
    const result = await api(
      "compute",
      `/api/v1/organizations/${encodeURIComponent(state.organizationId)}/computes`,
      "POST",
      {
        name: String(data.get("name")).trim(),
        image: String(data.get("image")).trim(),
        profile: String(data.get("profile")).trim(),
        ports: [],
      },
      { "Idempotency-Key": crypto.randomUUID() },
    );
    rememberOperation(result.operation, result.resource);
    $("#compute-dialog").close();
    form.reset();
    $("#compute-image").value = "approved-web";
    $("#compute-profile").value = "small";
    showToast("Compute request accepted. Provisioning is asynchronous.", "success");
    await loadComputes();
    await refreshOperationStatuses();
  } catch (error) {
    setInlineError("#compute-form-error", error.message);
  } finally {
    submit.disabled = false;
  }
}

async function submitOrganization(event) {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  const name = String(new FormData(event.currentTarget).get("name")).trim();
  setInlineError("#organization-form-error", "");
  submit.disabled = true;
  try {
    const organization = await api("iam", "/api/v1/organizations", "POST", { name });
    $("#organization-dialog").close();
    event.currentTarget.reset();
    await loadOrganizations();
    state.organizationId = organization.id;
    renderOrganizations();
    showToast(`Organization "${organization.name}" created.`, "success");
  } catch (error) {
    setInlineError("#organization-form-error", error.message);
  } finally {
    submit.disabled = false;
  }
}

async function performResourceAction(action, computeId) {
  const resource = state.computes.find((item) => item.id === computeId);
  if (!resource || !state.organizationId) return;
  if (action === "delete" && !window.confirm(`Delete "${resource.name}"? This is an asynchronous request.`)) return;
  const method = action === "delete" ? "DELETE" : "POST";
  const suffix = action === "delete" ? "" : `/${action}`;
  try {
    const result = await api(
      "compute",
      `/api/v1/organizations/${encodeURIComponent(state.organizationId)}/computes/${encodeURIComponent(computeId)}${suffix}`,
      method,
      undefined,
      { "Idempotency-Key": crypto.randomUUID() },
    );
    rememberOperation(result.operation, result.resource);
    showToast(`${action[0].toUpperCase()}${action.slice(1)} request accepted.`, "success");
    await loadComputes();
    await refreshOperationStatuses();
  } catch (error) {
    showToast(error.message);
  }
}

async function showResourceDetails(computeId) {
  if (!state.organizationId) return;
  try {
    const resource = await api(
      "compute",
      `/api/v1/organizations/${encodeURIComponent(state.organizationId)}/computes/${encodeURIComponent(computeId)}`,
    );
    $("#resource-dialog-title").textContent = resource.name;
    const fields = [
      ["Resource ID", resource.id],
      ["Organization", resource.organization_id],
      ["Image key", resource.image],
      ["Profile", resource.profile],
      ["Desired state", resource.desired_state],
      ["Observed state", resource.observed_state],
      ["Created", formatDate(resource.created_at)],
      ["Updated", formatDate(resource.updated_at)],
      ["Ports", resource.ports?.length ? JSON.stringify(resource.ports) : "No inbound mappings"],
    ];
    $("#resource-details").innerHTML = fields.map(([label, value]) => `
      <div class="detail-item"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong></div>
    `).join("");
    $("#resource-dialog").showModal();
  } catch (error) {
    showToast(error.message);
  }
}

function bindEvents() {
  $("#login-form").addEventListener("submit", signIn);
  $("#compute-form").addEventListener("submit", submitCompute);
  $("#organization-form").addEventListener("submit", submitOrganization);
  $("#logout-button").addEventListener("click", showLogin);
  $("#refresh-button").addEventListener("click", () => refreshDashboard());
  $("#compute-search").addEventListener("input", renderComputes);
  $("#organization-select").addEventListener("change", async (event) => {
    state.organizationId = event.target.value || null;
    renderOrganizations();
    try {
      await loadComputes();
      await refreshOperationStatuses();
    } catch (error) {
      showToast(error.message);
    }
  });
  $("#load-more").addEventListener("click", async () => {
    try {
      await loadComputes(true);
    } catch (error) {
      showToast(error.message);
    }
  });
  $("#create-organization-button").addEventListener("click", () => $("#organization-dialog").showModal());

  document.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const nav = target.closest("[data-view]");
    if (nav) {
      setActiveView(nav.dataset.view);
      return;
    }
    const navigate = target.closest("[data-navigate]");
    if (navigate) {
      setActiveView(navigate.dataset.navigate);
      return;
    }
    if (target.closest("[data-open-create]")) {
      if (!state.organizationId) {
        $("#organization-dialog").showModal();
        return;
      }
      setInlineError("#compute-form-error", "");
      $("#compute-dialog").showModal();
      return;
    }
    const closeButton = target.closest("[data-close-dialog]");
    if (closeButton) {
      $(`#${closeButton.dataset.closeDialog}`).close();
      return;
    }
    const organizationButton = target.closest("[data-select-org]");
    if (organizationButton) {
      state.organizationId = organizationButton.dataset.selectOrg;
      renderOrganizations();
      $("#organization-select").value = state.organizationId;
      try {
        await loadComputes();
        await refreshOperationStatuses();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }
    const actionButton = target.closest("[data-resource-action]");
    if (actionButton && !actionButton.disabled) {
      await performResourceAction(actionButton.dataset.resourceAction, actionButton.dataset.resourceId);
      return;
    }
    const detailsButton = target.closest("[data-resource-details]");
    if (detailsButton) await showResourceDetails(detailsButton.dataset.resourceDetails);
  });
}

bindEvents();
checkHealth();
window.setInterval(() => {
  if (state.token) refreshDashboard(true);
  else checkHealth();
}, 12000);
