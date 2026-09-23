/* 서버 호출만 담당한다.
 *
 * 이 파일에는 판정·계산이 없다. 점수를 만들거나 임계값과 비교하거나
 * 결측을 채우지 않는다. 서버가 준 값을 그대로 전달한다 (명세서 §11).
 */

async function request(method, path, { body, form } = {}) {
  const init = { method, headers: {} };
  if (form) {
    init.body = form;
  } else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(path, init);
  } catch (cause) {
    throw new ApiError("서버에 연결하지 못했습니다.", {
      code: "network_error", stage: "request",
    }, cause);
  }

  const text = await res.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = { raw: text }; }
  }

  if (!res.ok) {
    const detail = payload?.detail ?? payload ?? {};
    throw new ApiError(
      detail.message || `요청이 실패했습니다 (HTTP ${res.status})`,
      { code: detail.code, stage: detail.stage, detail: detail.detail,
        http: res.status },
    );
  }
  return payload;
}

export class ApiError extends Error {
  constructor(message, info = {}, cause) {
    super(message);
    this.name = "ApiError";
    this.info = info;
    this.cause = cause;
  }
}

export const api = {
  health: () => request("GET", "/health"),
  undecided: () => request("GET", "/health/config/undecided"),
  listUploads: () => request("GET", "/uploads"),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", "/uploads", { form });
  },
  validate: (id) => request("POST", `/uploads/${id}/validate`),
  mapping: (id) => request("POST", `/uploads/${id}/mapping`),
  confirmMapping: (id, decisions) =>
    request("POST", `/uploads/${id}/mapping/confirm`, { body: decisions }),
  subjects: (id) => request("GET", `/uploads/${id}/subjects`),
  analyze: (id, subjectId, filters) =>
    request("POST", `/uploads/${id}/analyze`,
      { body: { subject_id: subjectId, filters: filters || {} } }),
  evaluation: (runId) => request("GET", `/evaluations/${runId}`),
  runs: (id) => request("GET", `/uploads/${id}/runs`),
  createReport: (runId) => request("POST", "/reports", { body: { run_id: runId } }),
  aiExplain: (runId, dryRun = true) =>
    request("POST", `/ai/explain?dry_run=${dryRun ? "true" : "false"}`,
      { body: { run_id: runId } }),
  aiPolicy: () => request("GET", "/ai/policy"),
};
