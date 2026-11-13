// A line chart draws nothing for a series that has a single value (or values separated by gaps): there is no
// segment to draw. These helpers find such points so the chart can show them as dots.

/** Indexes of values with no neighbour on either side (the ends of the series count as empty). */
export function isolatedPointIndexes(values: ReadonlyArray<number | null | undefined>): Set<number> {
  const present = (i: number) => i >= 0 && i < values.length && values[i] !== null && values[i] !== undefined;
  const isolated = new Set<number>();
  values.forEach((_, i) => {
    if (present(i) && !present(i - 1) && !present(i + 1)) isolated.add(i);
  });
  return isolated;
}
