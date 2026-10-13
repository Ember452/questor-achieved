// preload：contextBridge 白名单出口。B2 阶段仅暴露 shellVersion 占位；
// B6 会扩展为 window.questorHost 五个方法（request / onServerEvent /
// respondToServerRequest / rejectServerRequest / getSnapshot），实现 Option A IPC 桥。
// 铁律：任何"业务方法"从 preload 直出即违反纯壳纪律（overview §14）；
// 一切业务调用统一走 request(method, params)。
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("questorHost", {
  shellVersion: "0.1.0",
});
