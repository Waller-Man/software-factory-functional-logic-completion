/** Flow estimate only: stage weights do not represent elapsed or remaining time. */
const stages: Record<string, readonly [number, number]> = {
  starting: [0, 2],
  extract_entities: [2, 8], generate_use_cases: [8, 14], describe_use_cases: [14, 20],
  generate_er_model: [20, 26], generate_crud: [26, 32], check_er_model: [32, 38],
  functional_requirements: [78, 84], external_interface: [84, 88], nonfunctional_requirements: [88, 92],
  use_case_plantuml: [92, 94], er_plantuml: [94, 96], save_docx: [96, 98], publishing: [98, 99],
};
const iterationStages = ['crud_check', 'complete_use_cases', 'complete_er_model', 'complete_crud'];

export class ProgressEstimate {
  private value = 0;
  constructor(private readonly maxIterations: number) {}

  advance(stage: string, status = 'running', iteration = 0, converged = false): number {
    let range = stages[stage];
    const index = iterationStages.indexOf(stage);
    if (index !== -1) {
      const round = Math.min(this.maxIterations, Math.max(1, Math.trunc(iteration)));
      const width = 40 / this.maxIterations;
      const start = 38 + (round - 1) * width + index * width / 4;
      range = [start, start + width / 4];
    }
    let next = range ? range[status === 'completed' ? 1 : 0] : this.value;
    if (stage === 'crud_check' && status === 'completed' && converged) next = 78;
    // Optional steps, early convergence and repeated messages must never move backwards.
    this.value = Math.max(this.value, Math.min(99, Math.floor(next)));
    return this.value;
  }

  finish(): number { return this.value = 100; }
}
