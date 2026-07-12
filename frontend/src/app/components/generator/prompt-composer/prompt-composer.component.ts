import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PromptMetadata } from '../../../services/brand.service';

interface SelectOption {
  value: string;
  label: string;
}

const OTHER = '__other__';

const TONE_OPTIONS: SelectOption[] = [
  { value: 'Factual', label: 'Factual' },
  { value: 'Engaging', label: 'Engaging' },
  { value: 'Optimistic', label: 'Optimistic' },
  { value: 'Sense of urgency', label: 'Sense of urgency' },
  { value: 'Financial', label: 'Financial' },
];

const AUDIENCE_OPTIONS: SelectOption[] = [
  { value: 'Internal team', label: 'Internal team' },
  { value: 'Board', label: 'Board' },
  { value: 'CEO', label: 'CEO' },
  { value: 'Client', label: 'Client' },
];

const STORY_OPTIONS: SelectOption[] = [
  { value: 'Customer centric', label: 'Customer centric' },
  { value: 'Creative', label: 'Creative' },
  { value: 'Data-driven narrative', label: 'Data-driven narrative' },
];

const VISUAL_RULES_OPTIONS: SelectOption[] = [
  { value: 'Use only library assets', label: 'Use only library assets' },
  { value: 'Use external assets', label: 'Use external assets' },
  { value: 'No restrictions', label: 'No restrictions' },
];

const OUTPUT_FORMAT_OPTIONS: SelectOption[] = [
  { value: 'Data driven', label: 'Data driven' },
  { value: 'Storytelling', label: 'Storytelling' },
  { value: 'Creative', label: 'Creative' },
  { value: 'Action oriented', label: 'Action oriented' },
];

@Component({
  selector: 'app-prompt-composer',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './prompt-composer.component.html',
  styleUrl: './prompt-composer.component.css'
})
export class PromptComposerComponent implements OnChanges {
  @Input() initialValues: Partial<PromptMetadata> | null = null;
  /** 'template-merge' oculta Slide Type/Visual Rules — ese pipeline no elige
   * layout ni assets, el template ya los fija (docs/designs/biblioteca-prompts-favoritos.md). */
  @Input() mode: 'synthesis' | 'template-merge' = 'synthesis';
  @Output() insert = new EventEmitter<{ text: string; metadata: PromptMetadata }>();

  readonly OTHER = OTHER;
  readonly toneOptions = TONE_OPTIONS;
  readonly audienceOptions = AUDIENCE_OPTIONS;
  readonly storyOptions = STORY_OPTIONS;
  readonly visualRulesOptions = VISUAL_RULES_OPTIONS;
  readonly outputFormatOptions = OUTPUT_FORMAT_OPTIONS;

  objective = '';
  slideType = '';
  noBuzzwords = false;

  toneSelect = '';
  toneOther = '';
  audienceSelect = '';
  audienceOther = '';
  storySelect = '';
  storyOther = '';
  visualRulesSelect = '';
  visualRulesOther = '';
  outputFormatSelect = '';
  outputFormatOther = '';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['initialValues'] && this.initialValues) {
      this.objective = this.initialValues.objective ?? this.objective;
      this.slideType = this.initialValues.slide_type ?? this.slideType;
      this.setSelectOrOther('tone', this.initialValues.tone, TONE_OPTIONS);
      this.setSelectOrOther('audience', this.initialValues.audience, AUDIENCE_OPTIONS);
      this.setSelectOrOther('story', this.initialValues.story, STORY_OPTIONS);
      this.setSelectOrOther('visualRules', this.initialValues.visual_rules, VISUAL_RULES_OPTIONS);
      this.setSelectOrOther('outputFormat', this.initialValues.output_format, OUTPUT_FORMAT_OPTIONS);
      if (this.initialValues.no_buzzwords !== undefined) this.noBuzzwords = this.initialValues.no_buzzwords;
    }
  }

  private setSelectOrOther(field: 'tone' | 'audience' | 'story' | 'visualRules' | 'outputFormat', value: string | undefined, options: SelectOption[]) {
    if (!value) return;
    const match = options.find(o => o.value === value);
    (this as any)[`${field}Select`] = match ? value : OTHER;
    if (!match) (this as any)[`${field}Other`] = value;
  }

  private resolve(select: string, other: string): string {
    return select === OTHER ? other.trim() : select;
  }

  get isValid(): boolean {
    return !!this.objective.trim();
  }

  assemble() {
    const tone = this.resolve(this.toneSelect, this.toneOther);
    const audience = this.resolve(this.audienceSelect, this.audienceOther);
    const story = this.resolve(this.storySelect, this.storyOther);
    const visualRules = this.resolve(this.visualRulesSelect, this.visualRulesOther);
    const outputFormat = this.resolve(this.outputFormatSelect, this.outputFormatOther);

    const metadata: PromptMetadata = {
      objective: this.objective.trim(),
      tone: tone || undefined,
      audience: audience || undefined,
      slide_type: this.slideType.trim() || undefined,
      story: story || undefined,
      visual_rules: visualRules || undefined,
      output_format: outputFormat || undefined,
      no_buzzwords: this.noBuzzwords,
    };

    const parts: string[] = [`Objective: ${metadata.objective}.`];
    if (tone) parts.push(`Tone: ${tone}.`);
    if (audience) parts.push(`Audience: ${audience}.`);
    if (metadata.slide_type) parts.push(`Slide type: ${metadata.slide_type}.`);
    if (story) parts.push(`Story: ${story}.`);
    if (visualRules) parts.push(`Visual rules: ${visualRules}.`);
    if (outputFormat) parts.push(`Output format: ${outputFormat}.`);
    if (this.noBuzzwords) parts.push('Avoid buzzwords.');

    this.insert.emit({ text: parts.join(' '), metadata });
  }
}
