import "@testing-library/jest-dom/vitest";

// jsdom has no layout, so it leaves out scrolling. The Chat thread auto-scrolls on an animation
// frame, which can land after a test ends and fail the run with "scrollTo is not a function".
if (!Element.prototype.scrollTo) Element.prototype.scrollTo = () => {};
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

import { afterEach as clearAfterEach } from "vitest";
clearAfterEach(() => { sessionStorage.clear(); });
