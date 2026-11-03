/** Flow estimates: the existing algorithm occupies 2–67%, illustrated output 67–98%. */
const coreStages: Record<string, readonly [number, number]> = {
  extract_entities: [2, 8], generate_use_cases: [8, 14], describe_use_cases: [14, 20],
  generate_er_model: [20, 26], generate_crud: [26, 32], check_er_model: [32, 38],
  functional_requirements: [78, 84], external_interface: [84, 88], nonfunctional_requirements: [88, 92],
  use_case_plantuml: [92, 94], er_plantuml: [94, 96], core_document: [96, 98],
};
const iterationStages = ['crud_check', 'complete_use_cases', 'complete_er_model', 'complete_crud'];
const outputStages: Record<string, readonly [number, number]> = {
  starting: [0, 2], render_environment: [2, 2], functional_hierarchy: [67, 73],
  layer_use_cases: [73, 84], leaf_activities: [84, 94], save_docx: [94, 98], publishing: [98, 99],
};

export class ProgressEstimate {
  private value = 0;
  constructor(private readonly maxIterations: number) {}

  advance(stage: string, status = 'running', iteration = 0, converged = false,
    completed = 0, total = 0): number {
    let range = coreStages[stage];
    const index = iterationStages.indexOf(stage);
    if (index !== -1) {
      const round = Math.min(this.maxIterations, Math.max(1, Math.trunc(iteration)));
      const width = 40 / this.maxIterations;
      const start = 38 + (round - 1) * width + index * width / 4;
      range = [start, start + width / 4];
    }
    let next = this.value;
    if (range) {
      const core = stage === 'crud_check' && status === 'completed' && converged
        ? 78 : range[status === 'completed' ? 1 : 0];
      next = 2 + (core - 2) * 65 / 96;
    } else if (outputStages[stage]) {
      const [start, end] = outputStages[stage];
      const fraction = status === 'completed' ? 1 : total > 0 ? Math.min(1, Math.max(0, completed / total)) : 0;
      next = start + (end - start) * fraction;
    }
    this.value = Math.max(this.value, Math.min(99, Math.floor(next)));
    return this.value;
  }

  finish(): number { return this.value = 100; }
}
