/* 홈 히어로 3D 오브젝트 — CSS transform 3D 로 그린다. 라이브러리 없음.
 *
 * 별도 모듈로 분리한 이유: 이 파일이 실패(네트워크·구문·미지원)해도
 * home.js 가 정적 대체 화면으로 진입할 수 있게 하기 위해서다 (명세서 §8).
 *
 * 화면 상태 저장 없음. 앱과 상태를 공유하지 않는다.
 */

const FACES = [
  ["f", "HS"], ["b", "KR"], ["l", "US"], ["r", "TW"], ["t", "VN"], ["d", "JP"],
];

export function supports3d() {
  return typeof CSS !== "undefined"
    && CSS.supports("transform-style", "preserve-3d")
    && CSS.supports("perspective", "1px");
}

/** 스테이지에 3D 오브젝트를 그린다. 성공하면 true. */
export function mount(stage) {
  if (!stage || !supports3d()) return false;

  const obj = document.createElement("div");
  obj.className = "obj";

  for (const cls of ["a", "b", "c", "eq"]) {
    const ring = document.createElement("div");
    ring.className = `obj__ring obj__ring--${cls}`;
    obj.append(ring);
  }

  const core = document.createElement("div");
  core.className = "obj__core";
  for (const [side, label] of FACES) {
    const face = document.createElement("div");
    face.className = `obj__face obj__face--${side}`;
    face.textContent = label;
    core.append(face);
  }
  const dot = document.createElement("div");
  dot.className = "obj__dot";
  core.append(dot);
  obj.append(core);

  stage.append(obj);
  stage.dataset["3d"] = "ready";
  return true;
}
