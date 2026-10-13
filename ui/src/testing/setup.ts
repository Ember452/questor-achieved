// vitest setup：注册 @testing-library/jest-dom 的 matchers（toBeInTheDocument 等），
// 让每条测文件不必各自 import。ADR-0031。
import "@testing-library/jest-dom/vitest";
