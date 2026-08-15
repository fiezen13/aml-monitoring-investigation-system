/**
 * Vật liệu dòng tiền cho polyline của Cesium.
 *
 * Cesium cho phép định nghĩa vật liệu bằng "fabric" — một mẩu GLSL chạy trên
 * từng fragment của đường, nhận `materialInput.st.s` là vị trí chuẩn hoá 0→1
 * dọc theo đường. Đó là đúng thứ cần: gói tiền chạy trên chính cung trắc địa đã
 * dựng, không phải một thực thể thứ hai bay theo.
 *
 * Vì sao không dịch chuyển toạ độ từng khung hình: một hành lang là 65 điểm
 * Cartesian; ba trăm hành lang là gần hai vạn điểm phải tính lại 60 lần mỗi
 * giây trên luồng chính. Đổi một uniform thì không tốn gì cả.
 *
 * Công thức trùng khít với shader của MapLibre (`maplibre/flowLayer.ts`) — đó
 * là điều kiện để cùng một hành lang, cùng một thời điểm, cho ra gói tiền ở
 * cùng một vị trí trên cả hai phép chiếu.
 */

import { Color, Event, Material } from "cesium";

import { flowMotion, type FlowAnimationSpec } from "../../../design/flow";
import { worldFlowClock } from "../state/flowClock";

const MATERIAL_TYPE = "F7FlowLine";

/**
 * `st.s` chạy dọc đường, `st.t` chạy ngang bề rộng.
 *
 * Dùng `diffuse` + `alpha` chứ không `emission`: `emission` bỏ qua ánh sáng
 * cảnh và làm đường sáng rực đúng kiểu neon mà bảng điều khiển này tránh.
 */
const SHADER_SOURCE = `
czm_material czm_getMaterial(czm_materialInput materialInput) {
  czm_material material = czm_getDefaultMaterial(materialInput);

  float progress = materialInput.st.s;
  float head = fract(time * speed + phase);
  float len = max(trailLength, 0.02);

  float behind = fract(head - progress);
  float t = 1.0 - clamp(behind / len, 0.0, 1.0);

  float body = t * t;
  float core = smoothstep(1.0 - coreRatio, 1.0, t);
  float intensity = body * 0.8 + core * 0.9;

  // Nét đứt của hành lang bình thường, giữ đúng chú giải dưới bản đồ.
  float dash = mix(1.0, step(0.45, fract(progress * 90.0)), dashed);

  // Mềm hai mép theo chiều ngang đường.
  float edge = 1.0 - smoothstep(0.55, 1.0, abs(materialInput.st.t * 2.0 - 1.0));

  material.diffuse = mix(color.rgb, vec3(1.0), core * 0.42);
  material.alpha = (baseOpacity * dash + intensity * trailOpacity) * edge;
  return material;
}
`;

/**
 * Đăng ký fabric vào kho vật liệu của Cesium.
 *
 * `_materialCache` là API nội bộ, nhưng đây là đúng cơ chế mà chính các vật
 * liệu polyline dựng sẵn của Cesium dùng (`PolylineGlow`, `PolylineDash`…):
 * `MaterialProperty.getType()` trả về một chuỗi, và chuỗi ấy phải tra được
 * trong kho này. Không có đường công khai nào thay thế cho vật liệu tuỳ biến
 * dùng với Entity.
 */
interface MaterialCache {
  _materialCache: {
    getMaterial(type: string): unknown;
    addMaterial(type: string, definition: unknown): void;
  };
}

let registered = false;

function registerFlowMaterial(): void {
  if (registered) return;
  const cache = (Material as unknown as MaterialCache)._materialCache;
  if (!cache.getMaterial(MATERIAL_TYPE)) {
    cache.addMaterial(MATERIAL_TYPE, {
      fabric: {
        type: MATERIAL_TYPE,
        uniforms: {
          color: new Color(1, 1, 1, 1),
          time: 0,
          speed: 0.08,
          phase: 0,
          trailLength: flowMotion.normalTrailLength,
          baseOpacity: flowMotion.baseOpacity,
          trailOpacity: flowMotion.trailOpacity,
          coreRatio: flowMotion.coreRatio,
          dashed: 0,
        },
        source: SHADER_SOURCE,
      },
      translucent: true,
    });
  }
  registered = true;
}

interface FlowUniformValues {
  color: Color;
  time: number;
  speed: number;
  phase: number;
  trailLength: number;
  baseOpacity: number;
  trailOpacity: number;
  coreRatio: number;
  dashed: number;
}

/**
 * Thuộc tính vật liệu của một hành lang.
 *
 * `isConstant = false` là điểm mấu chốt: Cesium sẽ tự gọi `getValue` ở mỗi
 * khung hình, và ta kéo thời gian từ đồng hồ dùng chung ngay tại đó. Nhờ vậy
 * lớp 3D không cần vòng lặp riêng, không cần ai đẩy dữ liệu vào — nó đọc đúng
 * con số mà bản đồ 2D đang đọc.
 *
 * `getValue` tái sử dụng object kết quả mà Cesium truyền vào, nên vòng lặp vẽ
 * không sinh rác.
 */
export class FlowMaterialProperty {
  private readonly _definitionChanged = new Event();
  private readonly color: Color;
  private readonly spec: FlowAnimationSpec;

  constructor(spec: FlowAnimationSpec) {
    registerFlowMaterial();
    this.spec = spec;
    this.color = Color.fromCssColorString(spec.color);
  }

  /**
   * Tốc độ 0 nghĩa là mô tả chuyển động đã nói "đứng yên" — chế độ giảm chuyển
   * động. Báo hằng số để Cesium thôi gọi lại `getValue` ở mỗi khung hình.
   */
  get isConstant(): boolean {
    return this.spec.speed === 0;
  }

  get definitionChanged(): Event {
    return this._definitionChanged;
  }

  getType(): string {
    return MATERIAL_TYPE;
  }

  getValue(_time: unknown, result?: Partial<FlowUniformValues>): FlowUniformValues {
    const out = (result ?? {}) as FlowUniformValues;
    out.color = Color.clone(this.color, out.color);
    out.time = worldFlowClock.time;
    out.speed = this.spec.speed;
    out.phase = this.spec.phase;
    out.trailLength = this.spec.trailLength;
    out.baseOpacity = this.spec.baseOpacity;
    out.trailOpacity = this.spec.trailOpacity;
    out.coreRatio = flowMotion.coreRatio;
    out.dashed = this.spec.dashed ? 1 : 0;
    return out;
  }

  equals(other?: unknown): boolean {
    return this === other;
  }
}
