import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BrandService, PortfolioItem, PromptIntent, PromptMetadata } from '../../services/brand.service';
import { AuthService } from '../../services/auth.service';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { interval, switchMap, takeWhile } from 'rxjs';
import { environment } from '../../../environments/environment';
import { triggerBlobDownload } from '../../utils/download.util';
import { PromptComposerComponent } from '../../components/generator/prompt-composer/prompt-composer.component';

@Component({
  selector: 'app-generator',
  standalone: true,
  imports: [CommonModule, FormsModule, PromptComposerComponent],
  templateUrl: './generator.component.html',
  styleUrl: './generator.component.css'
})
export class GeneratorComponent implements OnInit {
  brandService = inject(BrandService);
  authService = inject(AuthService);
  sanitizer = inject(DomSanitizer);

  get isSuperadmin(): boolean {
    return this.authService.currentUser?.role === 'superadmin';
  }

  // --- FORM DATA ---
  selectedBrandId: number | null = null;
  selectedStyle: string = '';
  selectedKnowledge: string = '';
  prompt: string = '';
  selectedRegion: string = '';
  allowAiImages: boolean = false;
  selectedFormat: string = 'pptx'; // 'pptx' or 'pdf_artistic'
  selectedTier: string = 'free'; // 'free' or 'premium' (Fix/Roadmap 1)
  
  // --- REVIEW SYSTEM ---
  currentJobId: number | null = null;
  showFeedbackModal: boolean = false;
  selectedRating: number = 0;
  feedbackComment: string = '';
  feedbackSubmitted: boolean = false;
  
  // --- OPTIONS ---
  brands: any[] = [];
  availableStyles: any[] = [];
  availableKnowledge: string[] = [];
  availableDialects: any[] = [];

  // --- STATE ---
  isGenerating: boolean = false;
  downloadUrl: any = '';
  errorMessage: string = '';

  // --- CONSOLE & LOGS ---
  synthesisLogs: { time: string, role: string, message: string }[] = [];
  progress: number = 0;
  currentStatus: string = '';

  // --- PROMPT SUPPORT (soporte-indicaciones) ---
  promptMetadata: PromptMetadata | null = null;

  showReuseModal: boolean = false;
  reusablePortfolios: PortfolioItem[] = [];
  loadingReusable: boolean = false;

  showIntentModal: boolean = false;
  promptIntents: PromptIntent[] = [];
  loadingIntents: boolean = false;

  showComposerModal: boolean = false;
  composerInitialValues: Partial<PromptMetadata> | null = null;

  ngOnInit() {
    this.loadBrands();
    this.loadMetadata();
    this.loadDialects();
  }

  loadDialects() {
    this.brandService.getAvailableDialects().subscribe({
      next: (res) => {
        console.log("[SynthesisStudio] Dialects loaded:", res);
        this.availableDialects = res || [];
        
        // Force UK if it exists in the response
        const uk = this.availableDialects.find(d => d.code === 'UK');
        if (uk) {
          this.selectedRegion = uk.code;
          console.log("[SynthesisStudio] Setting default to English (UK)");
        } else if (this.availableDialects.length > 0) {
          this.selectedRegion = this.availableDialects[0].code;
        }
      },
      error: (err) => console.error("[SynthesisStudio] Error loading dialects:", err)
    });
  }

  loadBrands() {
    this.brandService.getBrands().subscribe({
      next: (res) => {
        // Filtramos el ID -1 (Public Library) para que no aparezca como un "dossier" 
        // en la lista, ya que se maneja con la opción SUPERUSER.
        this.brands = res.filter((b: any) => b.id !== -1);
      }
    });
  }

  onBrandChange() {
    this.selectedStyle = '';
    this.selectedKnowledge = '';
    this.loadMetadata();
  }

  loadMetadata() {
    const brandId = (this.selectedBrandId === null) ? undefined : this.selectedBrandId;
    
    this.brandService.getAvailableStyles(brandId).subscribe({
      next: (res) => {
        this.availableStyles = res.styles || [];
        if (this.availableStyles.length === 1) {
          this.selectedStyle = this.availableStyles[0].filename;
        }
      }
    });

    this.brandService.getAvailableKnowledge(brandId).subscribe({
      next: (res) => {
        this.availableKnowledge = res.sources || [];
        if (this.availableKnowledge.length === 1) {
          this.selectedKnowledge = this.availableKnowledge[0];
        }
      }
    });
  }

  setPrompt(text: string) {
    this.prompt = text;
  }

  /** Reemplaza el textarea con confirmación si ya había contenido manual (no se pierde trabajo en silencio).
   * Devuelve false si el usuario canceló — los callers no deben aplicar el resto de su efecto (metadata, cerrar modal) en ese caso. */
  private applyPromptText(text: string): boolean {
    if (this.prompt.trim() && !confirm('This will replace your current prompt text. Continue?')) {
      return false;
    }
    this.prompt = text;
    return true;
  }

  // --- AYUDA 1: Reutilizar indicación anterior ---
  openReuseModal() {
    this.showReuseModal = true;
    this.loadingReusable = true;
    this.brandService.getLibraryPortfolios(this.selectedBrandId || undefined, { pageSize: 50 }).subscribe({
      next: (res) => {
        this.reusablePortfolios = (res.items || []).filter(p => p.has_prompt);
        this.loadingReusable = false;
      },
      error: () => { this.loadingReusable = false; }
    });
  }

  useAsBase(jobId: number) {
    this.brandService.getPortfolioDetail(jobId).subscribe({
      next: (detail) => {
        if (!this.applyPromptText(detail.prompt)) return;
        this.promptMetadata = detail.prompt_metadata;
        this.showReuseModal = false;
      },
      error: () => { this.errorMessage = 'Could not load that presentation as a base.'; }
    });
  }

  // --- AYUDA 2: Biblioteca de intenciones ---
  openIntentModal() {
    this.showIntentModal = true;
    this.loadingIntents = true;
    this.brandService.getPromptIntents().subscribe({
      next: (res) => {
        this.promptIntents = res || [];
        this.loadingIntents = false;
      },
      error: () => { this.loadingIntents = false; }
    });
  }

  selectIntent(intent: PromptIntent) {
    this.composerInitialValues = {
      objective: intent.label,
      tone: intent.expected_tone,
      story: intent.narrative_style,
      slide_type: intent.preferred_layouts?.[0] || '',
    };
    this.showIntentModal = false;
    this.showComposerModal = true;
  }

  // --- AYUDA 3: Compositor guiado + guía ---
  openComposerModal() {
    this.showComposerModal = true;
  }

  onComposerInsert(payload: { text: string; metadata: PromptMetadata }) {
    if (!this.applyPromptText(payload.text)) return;
    this.promptMetadata = payload.metadata;
    this.showComposerModal = false;
  }

  generate() {
    this.isGenerating = true;
    this.downloadUrl = '';
    this.errorMessage = '';
    this.synthesisLogs = [];
    this.progress = 0;
    this.addLog('Strategic Orchestrator', 'Initiating neural synthesis sequence...');
    console.log("[SynthesisStudio] allowAiImages state at call:", this.allowAiImages);
    
    this.brandService.generatePresentation({
      prompt: this.prompt,
      style_filename: this.selectedStyle,
      knowledge_filename: this.selectedKnowledge,
      region: this.selectedRegion,
      brand_id: this.selectedBrandId || undefined,
      allow_ai_images: this.allowAiImages,
      output_format: this.selectedFormat,
      tier: this.selectedTier,
      prompt_metadata: this.promptMetadata || undefined
    }).subscribe({
        next: (res: any) => {
          this.currentJobId = res.job_id;
          this.feedbackSubmitted = false;
          this.selectedRating = 0;
          this.feedbackComment = '';
          this.addLog('Analyst', 'Strategic command received and validated.');
          this.startPolling(res.job_id);
        },
        error: (err) => {
          this.isGenerating = false;
          this.errorMessage = err.error?.detail || 'Synthesis failed to initialize.';
        }
      });
  }

  private addLog(role: string, message: string) {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    this.synthesisLogs.push({ time, role, message });
    // Ampliamos el buffer para transparencia total (v12.0)
    if (this.synthesisLogs.length > 50) this.synthesisLogs.shift();
  }

  startPolling(jobId: string) {
    interval(2000)
      .pipe(
        switchMap(() => this.brandService.getGenerationStatus(jobId)),
        takeWhile((res: any) => res.status !== 'completed' && res.status !== 'error', true)
      )
      .subscribe({
        next: (res: any) => {
          this.progress = res.progress || 0;
          this.currentStatus = this.mapStatusToMessage(res.current_step || '');
          
          if (res.status === 'completed') {
            this.addLog('Strategic Orchestrator', 'Portfolio synthesis finalized and verified.');
            this.downloadUrl = environment.baseUrl + res.download_url;
            this.isGenerating = false;
          } else if (res.status === 'error') {
            this.errorMessage = res.current_step;
            this.isGenerating = false;
          } else {
            const lastLog = this.synthesisLogs[this.synthesisLogs.length - 1];
            const mappedRole = this.mapStatusToRole(res.current_step || '');
            const mappedMsg = this.mapStatusToMessage(res.current_step || '');
            if (lastLog?.message !== mappedMsg && mappedMsg) {
              this.addLog(mappedRole, mappedMsg);
            }
          }
        },
        error: () => {
          this.isGenerating = false;
          this.errorMessage = 'Communication link lost during synthesis.';
        }
      });
  }

  private mapStatusToRole(step: string): string {
    if (step.includes('Analyzing')) return 'Analyst';
    if (step.includes('Structuring')) return 'Architect';
    if (step.includes('Designing')) return 'Designer';
    if (step.includes('Rendering')) return 'Technician';
    return 'Strategist';
  }

  private mapStatusToMessage(step: string): string {
    return step.replace(/Gemini|Claude|OpenAI/gi, 'The Intelligence')
               .replace('Extracting', 'Mapping')
               .replace('Generating', 'Synthesizing');
  }

  reset() {
    this.isGenerating = false;
    this.downloadUrl = '';
    this.errorMessage = '';
    this.prompt = '';
    this.promptMetadata = null;
    this.synthesisLogs = [];
    this.currentJobId = null;
    this.showFeedbackModal = false;
    this.selectedRating = 0;
    this.feedbackComment = '';
    this.feedbackSubmitted = false;
    this.loadMetadata();
  }

  onDownloadClick() {
    if (!this.currentJobId) return;
    const extension = this.selectedFormat === 'pdf_artistic' ? 'pdf' : 'pptx';
    this.brandService.downloadPortfolio(this.currentJobId).subscribe({
      next: (blob) => triggerBlobDownload(blob, `presentation_${this.currentJobId}.${extension}`),
      error: () => { this.errorMessage = 'Download failed. Please try again.'; }
    });
    if (!this.feedbackSubmitted) {
      this.showFeedbackModal = true;
    }
  }

  selectRating(rating: number) {
    this.selectedRating = rating;
  }

  submitFeedback() {
    if (!this.currentJobId || this.selectedRating === 0) return;

    this.brandService.submitFeedback(this.currentJobId, this.selectedRating, this.feedbackComment).subscribe({
      next: (res) => {
        console.log("[SynthesisStudio] Feedback submitted successfully:", res);
        this.feedbackSubmitted = true;
        this.showFeedbackModal = false;
      },
      error: (err) => {
        console.error("[SynthesisStudio] Error submitting feedback:", err);
        this.showFeedbackModal = false;
      }
    });
  }
}
