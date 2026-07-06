import { Component, inject, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BrandService } from '../../services/brand.service';
import { AuthService } from '../../services/auth.service';
import { interval, Subscription, switchMap, takeWhile } from 'rxjs';

interface JobState {
  file: File | null;
  loading: boolean;
  status: string;
  progress: number;
  successMessage: string;
  errorMessage: string;
  visibilityScope: 'exclusive' | 'public';
  selectedBrandId: number | null;
  manualTags: string;
  pollingSub?: Subscription;
  logs: { time: string, role: string, message: string }[];
}

@Component({
  selector: 'app-brand-hub',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './brand-hub.component.html',
  styleUrl: './brand-hub.component.css'
})
export class BrandHubComponent implements OnInit, OnDestroy {
  brandService = inject(BrandService);
  authService = inject(AuthService);

  get isSuperadmin(): boolean {
    return this.authService.currentUser?.role === 'superadmin';
  }

  identityState: JobState = this.initialState();
  knowledgeState: JobState = this.initialState();
  assetState: JobState = this.initialState();

  officialBrands: any[] = [];
  newBrandName: string = '';
  showBrandCreator: boolean = false;

  resetLoading: boolean = false;

  // Footer Management Properties
  footers: any[] = [];
  isFooterEnabled: boolean = true;
  newFooter: any = { name: '', text: '', disclaimer: '' };
  logoLightFile: File | null = null;
  logoDarkFile: File | null = null;
  logoLightPreview: string = '';
  logoDarkPreview: string = '';
  isSavingFooter: boolean = false;
  showFooterCreator: boolean = false;

  ngOnInit() {
    this.loadBrands();
    this.loadFooters();
  }

  loadBrands() {
    this.brandService.getBrands().subscribe(res => {
      this.officialBrands = res.filter((b: any) => b.id !== -1);
    });
  }

  loadFooters() {
    this.brandService.getFooters().subscribe(res => {
      this.isFooterEnabled = res.is_footer_enabled;
      this.footers = res.footers;
    });
  }

  createNewBrand() {
    if (!this.newBrandName) return;
    this.brandService.createBrand(this.newBrandName).subscribe({
      next: (brand) => {
        this.officialBrands.push(brand);
        this.newBrandName = '';
        this.showBrandCreator = false;
      },
      error: (err) => alert(err.error?.detail || 'Error creating brand')
    });
  }

  private initialState(): JobState {
    return {
      file: null,
      loading: false,
      status: '',
      progress: 0,
      successMessage: '',
      errorMessage: '',
      visibilityScope: 'exclusive',
      selectedBrandId: null,
      manualTags: '',
      logs: []
    };
  }

  onFileSelected(event: any, type: 'brand_style' | 'knowledge' | 'pure_assets') {
    if (event.target.files.length > 0) {
      const file = event.target.files[0];
      if (type === 'brand_style') this.identityState.file = file;
      else if (type === 'knowledge') this.knowledgeState.file = file;
      else if (type === 'pure_assets') this.assetState.file = file;
    }
  }

  private addLog(state: JobState, role: string, message: string) {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    state.logs.push({ time, role, message });
    if (state.logs.length > 10) state.logs.shift();
  }

  upload(type: 'brand_style' | 'knowledge' | 'pure_assets') {
    let state: JobState;
    if (type === 'brand_style') state = this.identityState;
    else if (type === 'knowledge') state = this.knowledgeState;
    else state = this.assetState;

    if (!state.file) {
      state.errorMessage = 'Validation: Document required.';
      return;
    }

    if (state.visibilityScope === 'exclusive' && !state.selectedBrandId) {
      state.errorMessage = 'Validation: Please select a Brand from the official directory.';
      return;
    }
    
    state.loading = true;
    state.status = 'Initializing upload...';
    state.progress = 5;
    state.errorMessage = '';
    state.successMessage = '';
    state.logs = [];

    const role = type === 'brand_style' ? 'Designer' : 'Analyst';
    const brandName = this.officialBrands.find(b => b.id === state.selectedBrandId)?.name || 'Generic';
    
    this.addLog(state, 'Strategic Orchestrator', `Initiating ${type.replace('_', ' ')} for ${brandName} (${state.visibilityScope})...`);

    const filename = state.file.name;
    
    this.brandService.uploadBrandAsset(
      state.file, 
      type, 
      state.visibilityScope, 
      state.selectedBrandId || undefined, 
      state.manualTags
    ).subscribe({
      next: (res) => {
        this.addLog(state, role, 'Governance check passed. Starting extraction...');
        this.startPolling(filename, type);
      },
      error: (err) => {
        state.loading = false;
        state.errorMessage = err.error?.detail || err.message || 'Server timeout.';
      }
    });
  }

  startPolling(filename: string, type: 'brand_style' | 'knowledge' | 'pure_assets') {
    let state: JobState;
    if (type === 'brand_style') state = this.identityState;
    else if (type === 'knowledge') state = this.knowledgeState;
    else state = this.assetState;

    state.pollingSub?.unsubscribe();

    state.pollingSub = interval(2000)
      .pipe(
        switchMap(() => this.brandService.getIngestionStatus(filename, type)),
        takeWhile((res) => res.status !== 'completed' && res.status !== 'error', true)
      )
      .subscribe({
        next: (res) => {
          state.status = this.mapStatus(res.current_step);
          state.progress = res.progress || 0;

          const lastLog = state.logs[state.logs.length - 1];
          const mappedRole = this.mapRole(res.current_step, type);
          const mappedMsg = this.mapStatus(res.current_step);

          if (lastLog?.message !== mappedMsg && mappedMsg) {
            this.addLog(state, mappedRole, mappedMsg);
          }

          if (res.status === 'completed') {
            state.progress = 100;
            this.addLog(state, 'Strategic Orchestrator', 'Ingestion finalized and verified in Directory.');
            state.successMessage = 'Ingestion finalized successfully.';
            state.pollingSub?.unsubscribe();
            setTimeout(() => { state.loading = false; }, 5000);
          } else if (res.status === 'error') {
            state.loading = false;
            state.errorMessage = res.current_step;
            state.pollingSub?.unsubscribe();
          }
        },
        error: (err) => {
          state.loading = false;
          state.pollingSub?.unsubscribe();
        }
      });
  }

  private mapRole(step: string, type: string): string {
    if (!step) return type === 'brand_style' ? 'Designer' : 'Analyst';
    if (step.includes('Parsing')) return 'Analyst';
    if (step.includes('Indexing')) return 'Architect';
    if (step.includes('Harvest')) return 'Technician';
    return type === 'brand_style' ? 'Designer' : 'Analyst';
  }

  private mapStatus(step: string): string {
    if (!step) return '';
    return step.replace(/Gemini|Claude|OpenAI/gi, 'The Intelligence')
               .replace('Extracting', 'Mapping')
               .replace('Architected', 'Planned')
               .replace('Perfected', 'Finalized')
               .replace('Generating', 'Synthesizing');
  }

  reset(type: 'brand_style' | 'knowledge' | 'pure_assets') {
    const state = type === 'brand_style' ? this.identityState : (type === 'knowledge' ? this.knowledgeState : this.assetState);
    state.pollingSub?.unsubscribe();
    Object.assign(state, this.initialState());
  }

  resetAll() {
    if (!confirm('⚠️ This will DELETE all official brands, assets, and neural profiles.\n\nAre you sure?')) return;
    this.resetLoading = true;
    this.brandService.resetDatabase().subscribe({
      next: () => {
        this.resetLoading = false;
        this.identityState = this.initialState();
        this.knowledgeState = this.initialState();
        this.assetState = this.initialState();
        this.loadBrands();
      },
      error: () => { this.resetLoading = false; }
    });
  }

  onFooterLogoSelected(event: any, type: 'light' | 'dark') {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        if (type === 'light') {
          this.logoLightFile = file;
          this.logoLightPreview = reader.result as string;
        } else {
          this.logoDarkFile = file;
          this.logoDarkPreview = reader.result as string;
        }
      };
      reader.readAsDataURL(file);
    }
  }

  editFooter(f: any) {
    this.newFooter = {
      id: f.id,
      name: f.name,
      text: f.text,
      disclaimer: f.disclaimer
    };
    this.logoLightPreview = f.logo_light_path ? '/' + f.logo_light_path : '';
    this.logoDarkPreview = f.logo_dark_path ? '/' + f.logo_dark_path : '';
    this.logoLightFile = null;
    this.logoDarkFile = null;
    this.showFooterCreator = true;
  }

  clearFooterForm() {
    this.newFooter = { id: undefined, name: '', text: '', disclaimer: '' };
    this.logoLightFile = null;
    this.logoDarkFile = null;
    this.logoLightPreview = '';
    this.logoDarkPreview = '';
  }

  saveFooter() {
    if (!this.newFooter.name) return;
    this.isSavingFooter = true;
    this.brandService.createFooter(
      this.newFooter.name,
      this.newFooter.text,
      this.newFooter.disclaimer,
      this.logoLightFile || undefined,
      this.logoDarkFile || undefined,
      this.newFooter.id
    ).subscribe({
      next: (res) => {
        this.isSavingFooter = false;
        this.clearFooterForm();
        this.showFooterCreator = false;
        this.loadFooters();
      },
      error: (err) => {
        this.isSavingFooter = false;
        alert(err.error?.detail || 'Error saving footer config');
      }
    });
  }

  selectFooter(id: number) {
    this.brandService.selectFooter(id).subscribe({
      next: () => {
        this.newFooter = { id: undefined, name: '', text: '', disclaimer: '' }; // reset id so it reloads the active one
        this.loadFooters();
      },
      error: (err) => alert(err.error?.detail || 'Error selecting footer')
    });
  }

  deleteFooter(id: number) {
    if (!confirm('Are you sure you want to delete this footer template?')) return;
    this.brandService.deleteFooter(id).subscribe({
      next: () => {
        if (this.newFooter.id === id) {
          this.clearFooterForm();
        }
        this.loadFooters();
      },
      error: (err) => alert(err.error?.detail || 'Error deleting footer')
    });
  }

  toggleFooterGlobal(enabled: boolean) {
    this.brandService.toggleFooterGlobal(enabled).subscribe({
      next: () => this.isFooterEnabled = enabled,
      error: (err) => alert(err.error?.detail || 'Error toggling footer')
    });
  }

  ngOnDestroy() {
    this.identityState.pollingSub?.unsubscribe();
    this.knowledgeState.pollingSub?.unsubscribe();
    this.assetState.pollingSub?.unsubscribe();
  }
}
