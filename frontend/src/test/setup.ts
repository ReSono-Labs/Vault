import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

import { afterEach as clearAfterEach } from "vitest";
clearAfterEach(() => { sessionStorage.clear(); });
