import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SimpleChange } from '@angular/core';
import { PromptComposerComponent } from './prompt-composer.component';

describe('PromptComposerComponent', () => {
  let fixture: ComponentFixture<PromptComposerComponent>;
  let component: PromptComposerComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PromptComposerComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(PromptComposerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  describe('isValid', () => {
    it('is false when objective is empty', () => {
      component.objective = '';
      expect(component.isValid).toBeFalse();
    });

    it('is false when objective is only whitespace', () => {
      component.objective = '   ';
      expect(component.isValid).toBeFalse();
    });

    it('is true once objective has text', () => {
      component.objective = 'CEO Board Update';
      expect(component.isValid).toBeTrue();
    });
  });

  describe('assemble()', () => {
    it('emits objective-only text when no other fields are set', (done) => {
      component.objective = 'CEO Board Update';
      component.insert.subscribe((payload) => {
        expect(payload.text).toBe('Objective: CEO Board Update.');
        expect(payload.metadata.objective).toBe('CEO Board Update');
        expect(payload.metadata.tone).toBeUndefined();
        done();
      });
      component.assemble();
    });

    it('assembles all fields from preset selects in the documented order', (done) => {
      component.objective = 'Q3 Sales Review';
      component.toneSelect = 'Engaging';
      component.audienceSelect = 'Board';
      component.slideType = 'data grid';
      component.storySelect = 'Customer centric';
      component.visualRulesSelect = 'No restrictions';
      component.outputFormatSelect = 'Data driven';
      component.noBuzzwords = true;

      component.insert.subscribe((payload) => {
        expect(payload.text).toBe(
          'Objective: Q3 Sales Review. Tone: Engaging. Audience: Board. Slide type: data grid. ' +
          'Story: Customer centric. Visual rules: No restrictions. Output format: Data driven. Avoid buzzwords.'
        );
        expect(payload.metadata).toEqual({
          objective: 'Q3 Sales Review',
          tone: 'Engaging',
          audience: 'Board',
          slide_type: 'data grid',
          story: 'Customer centric',
          visual_rules: 'No restrictions',
          output_format: 'Data driven',
          no_buzzwords: true,
        });
        done();
      });
      component.assemble();
    });

    it('uses the free-text field when "Other..." is selected', (done) => {
      component.objective = 'Investor pitch';
      component.toneSelect = component.OTHER;
      component.toneOther = 'Bold and confident';

      component.insert.subscribe((payload) => {
        expect(payload.metadata.tone).toBe('Bold and confident');
        expect(payload.text).toContain('Tone: Bold and confident.');
        done();
      });
      component.assemble();
    });

    it('trims whitespace from the free-text "Other" value', (done) => {
      component.objective = 'Investor pitch';
      component.audienceSelect = component.OTHER;
      component.audienceOther = '   Regional VPs   ';

      component.insert.subscribe((payload) => {
        expect(payload.metadata.audience).toBe('Regional VPs');
        done();
      });
      component.assemble();
    });

    it('trims the objective', (done) => {
      component.objective = '  Leading with data  ';
      component.insert.subscribe((payload) => {
        expect(payload.metadata.objective).toBe('Leading with data');
        done();
      });
      component.assemble();
    });
  });

  describe('ngOnChanges — prefill from initialValues', () => {
    it('restores objective, slide_type and tone (matching a preset option)', () => {
      component.initialValues = { objective: 'Executive Presentation', tone: 'Formal, authoritative', slide_type: 'cover_hero' };
      component.ngOnChanges({ initialValues: new SimpleChange(null, component.initialValues, true) });

      expect(component.objective).toBe('Executive Presentation');
      expect(component.slideType).toBe('cover_hero');
      // 'Formal, authoritative' no está en TONE_OPTIONS -> cae a Other + texto libre
      expect(component.toneSelect).toBe(component.OTHER);
      expect(component.toneOther).toBe('Formal, authoritative');
    });

    it('restores tone as a matched preset (not Other) when the value is a known option', () => {
      component.initialValues = { objective: 'X', tone: 'Engaging' };
      component.ngOnChanges({ initialValues: new SimpleChange(null, component.initialValues, true) });

      expect(component.toneSelect).toBe('Engaging');
      expect(component.toneOther).toBe('');
    });

    it('restores audience, story, visual_rules and output_format (all five fields, not just tone/story)', () => {
      component.initialValues = {
        objective: 'X',
        audience: 'Board',
        story: 'Creative',
        visual_rules: 'No restrictions',
        output_format: 'Storytelling',
      };
      component.ngOnChanges({ initialValues: new SimpleChange(null, component.initialValues, true) });

      expect(component.audienceSelect).toBe('Board');
      expect(component.storySelect).toBe('Creative');
      expect(component.visualRulesSelect).toBe('No restrictions');
      expect(component.outputFormatSelect).toBe('Storytelling');
    });

    it('restores no_buzzwords flag', () => {
      component.initialValues = { objective: 'X', no_buzzwords: true };
      component.ngOnChanges({ initialValues: new SimpleChange(null, component.initialValues, true) });

      expect(component.noBuzzwords).toBeTrue();
    });

    it('does nothing when initialValues is null', () => {
      component.objective = 'existing';
      component.initialValues = null;
      component.ngOnChanges({ initialValues: new SimpleChange({}, null, false) });

      expect(component.objective).toBe('existing');
    });
  });
});
