/**
 * Lớp vẽ dòng tiền chảy trên bản đồ phẳng — WebGL thuần, một draw call.
 *
 * Vì sao không dùng lớp `line` của MapLibre: một lớp `line` chỉ có **một**
 * `line-gradient` cho toàn bộ lớp, nên mọi hành lang buộc phải chảy cùng pha —
 * nhìn ra ngay là hiệu ứng trang trí chứ không phải dữ liệu. Muốn mỗi hành lang
 * một pha, một tốc độ, một chiều dài vệt riêng thì phải xuống tới shader.
 *
 * Phân vai:
 *
 *   lớp này         →  toàn bộ phần nhìn thấy: đường nền mờ + vệt tiền đang chảy
 *   lớp GeoJSON     →  vùng bắt chuột trong suốt (`layers.ts`), giữ nguyên
 *                      hit-test và xử lý kinh tuyến 180° đã đúng sẵn
 *
 * Hình học được dựng **một lần** mỗi khi tập hành lang đổi (đổi bộ lọc, đổi
 * Top N, đổi lựa chọn). Mỗi khung hình chỉ đổi đúng một uniform `u_time`. Không
 * có `setData` trong vòng lặp vẽ, không có cấp phát mới mỗi khung hình.
 */

import {
  MercatorCoordinate,
  type CustomLayerInterface,
  type CustomRenderMethodInput,
  type Map as MapLibreMap,
} from "maplibre-gl";

import { flowMotion, type FlowAnimationSpec } from "../../../design/flow";
import { build2DRouteGeometry } from "../adapters/routeGeometry";
import type { RouteDescriptor } from "../adapters/toCesium";
import { worldFlowClock } from "../state/flowClock";

export const FLOW_LAYER_ID = "aml-route-flow";

/** Số float cho mỗi đỉnh. Xem `pushVertex` để biết thứ tự. */
const STRIDE = 16;

const VERTEX_SOURCE = `#version 300 es
precision highp float;

in vec2 a_pos;        // toạ độ mercator 0..1
in vec2 a_normal;     // pháp tuyến đơn vị trong không gian mercator
in float a_side;      // -1 hoặc +1
in vec4 a_flow;       // progress, phase, speed, trailLength
in vec3 a_color;
in vec4 a_style;      // baseOpacity, trailOpacity, width(px), dashed

uniform mat4 u_matrix;
uniform float u_unitsPerPixel;
uniform float u_widthScale;

out float v_progress;
out float v_phase;
out float v_speed;
out float v_trail;
out vec3 v_color;
out float v_base;
out float v_trailOpacity;
out float v_dashed;
out float v_side;

void main() {
  // Bề rộng tính bằng pixel màn hình rồi đổi sang đơn vị mercator: đường phải
  // giữ nguyên độ dày khi phóng to thu nhỏ, giống mọi đường khác trên bản đồ.
  float halfWidth = max(a_style.z * u_widthScale, 0.6) * 0.5;
  vec2 offset = a_normal * a_side * halfWidth * u_unitsPerPixel;
  gl_Position = u_matrix * vec4(a_pos + offset, 0.0, 1.0);

  v_progress = a_flow.x;
  v_phase = a_flow.y;
  v_speed = a_flow.z;
  v_trail = a_flow.w;
  v_color = a_color;
  v_base = a_style.x;
  v_trailOpacity = a_style.y;
  v_dashed = a_style.w;
  v_side = a_side;
}`;

const FRAGMENT_SOURCE = `#version 300 es
precision highp float;

uniform float u_time;
uniform float u_trailScale;
uniform float u_opacityScale;
uniform float u_coreRatio;

in float v_progress;
in float v_phase;
in float v_speed;
in float v_trail;
in vec3 v_color;
in float v_base;
in float v_trailOpacity;
in float v_dashed;
in float v_side;

out vec4 fragColor;

void main() {
  // Đầu gói chạy từ nguồn (progress 0) tới đích (progress 1). Hướng dòng tiền
  // đọc được ngay từ chiều chuyển động, không cần mũi tên.
  float head = fract(u_time * v_speed + v_phase);
  float trailLength = max(v_trail * u_trailScale, 0.02);

  // Khoảng cách tính NGƯỢC từ đầu gói về phía đuôi; fract() lo phần vòng lại.
  float behind = fract(head - v_progress);
  float t = 1.0 - clamp(behind / trailLength, 0.0, 1.0);

  // Thân mềm dần về đuôi, cộng một lõi nóng rất ngắn ở đầu. Đây là chỗ tạo ra
  // cảm giác "gói dữ liệu" thay vì "chấm tròn chạy trên đường".
  float body = t * t;
  float core = smoothstep(1.0 - u_coreRatio, 1.0, t);
  float intensity = body * 0.8 + core * 0.9;

  // Nét đứt chỉ áp lên đường nền của hành lang bình thường — giữ đúng chú giải
  // "nét đứt = bình thường". Vệt chảy không bị cắt vụn theo nét đứt.
  float dash = mix(1.0, step(0.45, fract(v_progress * 90.0)), v_dashed);

  // Làm mềm hai mép để đường không răng cưa; đây là khử răng cưa duy nhất vì
  // lớp vẽ trong cùng framebuffer với bản đồ.
  float edge = 1.0 - smoothstep(0.55, 1.0, abs(v_side));

  float alpha = (v_base * dash + intensity * v_trailOpacity) * edge * u_opacityScale;
  vec3 color = mix(v_color, vec3(1.0), core * 0.42);

  // Alpha nhân sẵn: MapLibre đặt blendFunc(ONE, ONE_MINUS_SRC_ALPHA).
  fragColor = vec4(color * alpha, alpha);
}`;

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`[flow] shader lỗi: ${log}`);
  }
  return shader;
}

interface Attribs {
  pos: number;
  normal: number;
  side: number;
  flow: number;
  color: number;
  style: number;
}

interface Uniforms {
  matrix: WebGLUniformLocation | null;
  unitsPerPixel: WebGLUniformLocation | null;
  widthScale: WebGLUniformLocation | null;
  time: WebGLUniformLocation | null;
  trailScale: WebGLUniformLocation | null;
  opacityScale: WebGLUniformLocation | null;
  coreRatio: WebGLUniformLocation | null;
}

/** Chuyển mã màu `#rrggbb` sang ba thành phần 0–1. Gọi lúc dựng buffer, không phải mỗi khung hình. */
function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  const full = value.length === 3 ? value.replace(/./g, (c) => c + c) : value;
  const int = Number.parseInt(full, 16);
  return [((int >> 16) & 255) / 255, ((int >> 8) & 255) / 255, (int & 255) / 255];
}

export class FlowLayer implements CustomLayerInterface {
  readonly id = FLOW_LAYER_ID;
  readonly type = "custom" as const;
  readonly renderingMode = "2d" as const;

  private gl: WebGL2RenderingContext | null = null;
  private map: MapLibreMap | null = null;
  private program: WebGLProgram | null = null;
  private buffer: WebGLBuffer | null = null;
  private vao: WebGLVertexArrayObject | null = null;
  private attribs: Attribs | null = null;
  private uniforms: Uniforms | null = null;
  private vertexCount = 0;

  /** Dữ liệu chờ nạp khi lớp chưa được gắn vào map. */
  private pending: Float32Array | null = null;

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    this.gl = gl;

    const program = gl.createProgram()!;
    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX_SOURCE);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SOURCE);
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`[flow] link chương trình lỗi: ${gl.getProgramInfoLog(program)}`);
    }
    this.program = program;

    this.attribs = {
      pos: gl.getAttribLocation(program, "a_pos"),
      normal: gl.getAttribLocation(program, "a_normal"),
      side: gl.getAttribLocation(program, "a_side"),
      flow: gl.getAttribLocation(program, "a_flow"),
      color: gl.getAttribLocation(program, "a_color"),
      style: gl.getAttribLocation(program, "a_style"),
    };
    this.uniforms = {
      matrix: gl.getUniformLocation(program, "u_matrix"),
      unitsPerPixel: gl.getUniformLocation(program, "u_unitsPerPixel"),
      widthScale: gl.getUniformLocation(program, "u_widthScale"),
      time: gl.getUniformLocation(program, "u_time"),
      trailScale: gl.getUniformLocation(program, "u_trailScale"),
      opacityScale: gl.getUniformLocation(program, "u_opacityScale"),
      coreRatio: gl.getUniformLocation(program, "u_coreRatio"),
    };

    this.buffer = gl.createBuffer();
    this.vao = gl.createVertexArray();
    this.bindVertexArray();

    if (this.pending) {
      this.upload(this.pending);
      this.pending = null;
    }
  }

  private bindVertexArray(): void {
    const { gl, attribs } = this;
    if (!gl || !attribs || !this.vao || !this.buffer) return;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    const bytes = STRIDE * 4;
    const set = (loc: number, size: number, offset: number) => {
      if (loc < 0) return;
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, bytes, offset * 4);
    };
    set(attribs.pos, 2, 0);
    set(attribs.normal, 2, 2);
    set(attribs.side, 1, 4);
    set(attribs.flow, 4, 5);
    set(attribs.color, 3, 9);
    set(attribs.style, 4, 12);
    gl.bindVertexArray(null);
  }

  onRemove(): void {
    const gl = this.gl;
    if (!gl) return;
    if (this.program) gl.deleteProgram(this.program);
    if (this.buffer) gl.deleteBuffer(this.buffer);
    if (this.vao) gl.deleteVertexArray(this.vao);
    this.program = null;
    this.buffer = null;
    this.vao = null;
    this.gl = null;
    this.map = null;
    this.vertexCount = 0;
  }

  /**
   * Dựng lại hình học. Gọi khi tập hành lang, bộ lọc hoặc lựa chọn đổi — KHÔNG
   * gọi mỗi khung hình.
   */
  setRoutes(routes: RouteDescriptor[], specs: Map<string, FlowAnimationSpec>): void {
    const data = buildVertexData(routes, specs);
    if (this.gl && this.buffer) this.upload(data);
    else this.pending = data;
  }

  private upload(data: Float32Array): void {
    const gl = this.gl;
    if (!gl || !this.buffer) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
    this.vertexCount = data.length / STRIDE;
  }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void {
    if (!this.program || !this.vao || !this.uniforms || !this.map || this.vertexCount === 0) return;

    const zoom = this.map.getZoom();
    // Kích thước thế giới tính bằng pixel ở mức phóng hiện tại. Toạ độ mercator
    // chạy 0..1 trên toàn thế giới, nên một pixel bằng 1/worldSize đơn vị.
    const worldSize = 512 * 2 ** zoom;

    const { lod } = flowMotion;
    const near = Math.min(1, Math.max(0, (zoom - lod.farZoom) / (lod.nearZoom - lod.farZoom)));
    const widthScale = lod.farWidthScale + (1 - lod.farWidthScale) * near;
    const trailScale = lod.farTrailScale + (1 - lod.farTrailScale) * near;
    const opacityScale = lod.farOpacityScale + (1 - lod.farOpacityScale) * near;

    gl.useProgram(this.program);
    gl.uniformMatrix4fv(this.uniforms.matrix, false, args.defaultProjectionData.mainMatrix);
    gl.uniform1f(this.uniforms.unitsPerPixel, 1 / worldSize);
    gl.uniform1f(this.uniforms.widthScale, widthScale);
    gl.uniform1f(this.uniforms.time, worldFlowClock.time);
    gl.uniform1f(this.uniforms.trailScale, trailScale);
    gl.uniform1f(this.uniforms.opacityScale, opacityScale);
    gl.uniform1f(this.uniforms.coreRatio, flowMotion.coreRatio);

    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, this.vertexCount);
    gl.bindVertexArray(null);
  }
}

/**
 * Dựng dải tam giác cho toàn bộ hành lang.
 *
 * Một buffer duy nhất cho mọi hành lang, nối với nhau bằng đỉnh suy biến
 * (degenerate) — nhờ vậy cả màn hình chỉ tốn một `drawArrays`, dù có ba trăm
 * hành lang hay ba mươi.
 *
 * `progress` được tính theo chiều dài tích luỹ của **cả** hành lang, kể cả khi
 * nó bị cắt làm nhiều đoạn ở kinh tuyến 180°: gói tiền phải chạy liên tục từ
 * nguồn tới đích chứ không khởi động lại ở mỗi mảnh.
 */
export function buildVertexData(
  routes: RouteDescriptor[],
  specs: Map<string, FlowAnimationSpec>,
): Float32Array {
  const out: number[] = [];
  let vertexCount = 0;

  const push = (
    x: number,
    y: number,
    nx: number,
    ny: number,
    side: number,
    progress: number,
    spec: FlowAnimationSpec,
    rgb: [number, number, number],
  ) => {
    out.push(
      x,
      y,
      nx,
      ny,
      side,
      progress,
      spec.phase,
      spec.speed,
      spec.trailLength,
      rgb[0],
      rgb[1],
      rgb[2],
      spec.baseOpacity,
      spec.trailOpacity,
      spec.width,
      spec.dashed ? 1 : 0,
    );
    vertexCount += 1;
  };

  for (const route of routes) {
    const spec = specs.get(route.id);
    if (!spec) continue;
    const rgb = hexToRgb(spec.color);

    const segments = build2DRouteGeometry(
      [route.from.lon, route.from.lat],
      [route.to.lon, route.to.lat],
    );

    // Chiếu sang mercator một lần, và đo tổng chiều dài để chuẩn hoá progress.
    const projected = segments.map((segment) =>
      segment.map(([lon, lat]) => {
        const mercator = MercatorCoordinate.fromLngLat({ lng: lon, lat });
        return [mercator.x, mercator.y] as [number, number];
      }),
    );

    let totalLength = 0;
    for (const segment of projected) {
      for (let i = 1; i < segment.length; i++) {
        totalLength += Math.hypot(segment[i][0] - segment[i - 1][0], segment[i][1] - segment[i - 1][1]);
      }
    }
    if (totalLength <= 0) continue;

    let walked = 0;
    for (const segment of projected) {
      if (segment.length < 2) continue;

      for (let i = 0; i < segment.length; i++) {
        const [x, y] = segment[i];
        if (i > 0) {
          walked += Math.hypot(x - segment[i - 1][0], y - segment[i - 1][1]);
        }
        const progress = walked / totalLength;

        // Pháp tuyến lấy từ hướng trung bình của hai cạnh kề, nên chỗ gấp khúc
        // không bị thắt lại.
        const prev = segment[Math.max(0, i - 1)];
        const next = segment[Math.min(segment.length - 1, i + 1)];
        let dx = next[0] - prev[0];
        let dy = next[1] - prev[1];
        const length = Math.hypot(dx, dy) || 1;
        dx /= length;
        dy /= length;
        const nx = -dy;
        const ny = dx;

        // Đỉnh suy biến ở đầu mỗi đoạn: nối dải tam giác này với dải trước mà
        // không vẽ ra một tam giác nhìn thấy được.
        if (i === 0 && vertexCount > 0) {
          push(x, y, nx, ny, -1, progress, spec, rgb);
        }
        push(x, y, nx, ny, -1, progress, spec, rgb);
        push(x, y, nx, ny, 1, progress, spec, rgb);
        if (i === segment.length - 1) {
          push(x, y, nx, ny, 1, progress, spec, rgb);
        }
      }
    }
  }

  return new Float32Array(out);
}
