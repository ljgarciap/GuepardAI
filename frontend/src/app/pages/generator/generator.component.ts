import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BrandService } from '../../services/brand.service';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { interval, switchMap, takeWhile } from 'rxjs';

@Component({
  selector: 'app-generator',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './generator.component.html',
  styleUrl: './generator.component.css'
})
export class GeneratorComponent implements OnInit {
  brandService = inject(BrandService);
  sanitizer = inject(DomSanitizer);

  // --- FORM DATA ---
  selectedStyle: string = '';
  selectedKnowledge: string = '';
  prompt: string = '';
  selectedRegion: string = 'LATAM';
  
  // --- OPTIONS ---
  availableStyles: any[] = [];
  availableKnowledge: string[] = [];

  // --- STATE ---
  isGenerating: boolean = false;
  downloadUrl: any = '';
  errorMessage: string = '';

  // --- CONSOLE & LOGS ---
  synthesisLogs: { time: string, role: string, message: string }[] = [];
  progress: number = 0;
  currentStatus: string = '';

  ngOnInit() {
    this.loadMetadata();
  }

  loadMetadata() {
    this.brandService.getAvailableStyles().subscribe({
      next: (res) => {
        this.availableStyles = res.styles || [];
        if (this.availableStyles.length === 1) {
          this.selectedStyle = this.availableStyles[0].filename;
        }
      }
    });

    this.brandService.getAvailableKnowledge().subscribe({
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

  generate() {
    this.isGenerating = true;
    this.downloadUrl = '';
    this.errorMessage = '';
    this.synthesisLogs = [];
    this.progress = 0;
    this.addLog('Strategic Orchestrator', 'Initiating neural synthesis sequence...');
    
    this.brandService.generatePresentation(this.prompt, this.selectedStyle, this.selectedKnowledge, this.selectedRegion)
      .subscribe({
        next: (res: any) => {
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
    if (this.synthesisLogs.length > 10) this.synthesisLogs.shift();
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
            this.downloadUrl = res.download_url;
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
    this.synthesisLogs = [];
    this.loadMetadata();
  }
}
