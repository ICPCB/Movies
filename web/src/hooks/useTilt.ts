import { useCallback, useRef } from "react";

/**
 * Pointer-tracked 3D tilt with a moving glare highlight.
 * Returns a ref plus pointer handlers to spread on the tilting element.
 * The element should sit inside a parent with CSS `perspective`.
 * Respects prefers-reduced-motion (no tilt at all).
 */
export function useTilt(maxDeg = 7) {
  const ref = useRef<HTMLDivElement>(null);
  const frame = useRef(0);

  const reducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (reducedMotion || event.pointerType === "touch") return;
      const node = ref.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width; // 0..1
      const py = (event.clientY - rect.top) / rect.height; // 0..1
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        node.style.transform = `rotateX(${(0.5 - py) * maxDeg * 2}deg) rotateY(${
          (px - 0.5) * maxDeg * 2
        }deg) scale3d(1.03, 1.03, 1.03)`;
        node.style.setProperty("--glare-x", `${px * 100}%`);
        node.style.setProperty("--glare-y", `${py * 100}%`);
        node.style.setProperty("--glare-o", "1");
      });
    },
    [maxDeg, reducedMotion],
  );

  const onPointerLeave = useCallback(() => {
    const node = ref.current;
    if (!node) return;
    cancelAnimationFrame(frame.current);
    node.style.transform = "";
    node.style.setProperty("--glare-o", "0");
  }, []);

  return { ref, onPointerMove, onPointerLeave };
}
