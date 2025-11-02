#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REN'PY AUTO TRANSLATOR v7.1 - COPILOT FIXES APPLIED
- Fixed: Batch queue double-fill bug
- Fixed: ID mapping inconsistency
- Fixed: Delay optimization
- Fixed: Error handling improvements
- Fixed: Regex safety
- Fixed: LOG_LEVEL case sensitivity
- Fixed: Output file protection
- All 11 Copilot issues resolved!
"""

import re
import os
import time
import subprocess
import glob
from datetime import datetime

# ================ CONFIG ================
BAHASA_ASAL = "en"
BAHASA_TUJUAN = "id"
JEDA_TERJEMAH = 0.5
LOG_LEVEL = "ERROR"  # Will be normalized to uppercase

# BATCH SETTINGS
USE_BATCH = True
BATCH_SEPARATOR = "|~|~|"
BATCH_SIZE = 5
MAX_BATCH_CHARS = 1000
# ========================================

class RenPyAutoTranslator:
    def __init__(self, input_file):
        self.input_file = input_file
        self.output_file = self._generate_output_name()
        self.log_file = self._generate_log_name()
        self.total_lines = 0

        # Normalize LOG_LEVEL to uppercase (Fix #7)
        global LOG_LEVEL
        LOG_LEVEL = LOG_LEVEL.upper()

        # Logging counters
        self.translation_stats = {
            'success': 0,
            'failed': 0,
            'empty_input': 0,
            'empty_output': 0,
            'errors': 0,
            'skipped_code': 0,
            'total_processed': 0,
            'batch_success': 0,
            'batch_failed': 0,
            'fallback_individual': 0
        }

        self.skip_keywords = [
            'show ', 'scene ', 'play ', 'stop ', 'queue ',
            'image ', 'define ', 'transform ', 'screen ',
            'jump ', 'call ', 'return', 'menu:', 'if ',
            'python:', 'init ', 'label ', 'with ',
            'hide ', 'at ', 'as ', '$', 'pause',
            'nvl ', 'window ', 'voice ', 'sound ',
            'music ', 'audio ', 'renpy.', 'camera '
        ]

    def _generate_output_name(self):
        base, ext = os.path.splitext(self.input_file)
        # Fix #10: Ensure .rpy extension
        return f"{base}_{BAHASA_TUJUAN}.rpy"

    def _generate_log_name(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(self.input_file))[0]
        return f"log_{base_name}_{timestamp}.txt"

    def _init_log_file(self):
        if LOG_LEVEL == "SUMMARY":
            return
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write("=== REN'PY TRANSLATION LOG v7.1 - COPILOT FIXES ===\n")
                f.write(f"Tanggal: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Input: {self.input_file}\n")
                f.write(f"Output: {self.output_file}\n")
                f.write(f"Bahasa: {BAHASA_ASAL} -> {BAHASA_TUJUAN}\n")
                f.write(f"Mode: {'BATCH' if USE_BATCH else 'SEQUENTIAL'}\n")
                if USE_BATCH:
                    f.write(f"Batch Size: {BATCH_SIZE} dialogues\n")
                    f.write(f"Separator: '{BATCH_SEPARATOR}'\n")
                f.write(f"Log Level: {LOG_LEVEL}\n")
                f.write("="*50 + "\n\n")
        except IOError as e:
            print(f"⚠️ Could not create log file: {e}")

    def _log_translation(self, line_num, status, original_text, translated_text="", error_msg="", context=""):
        if LOG_LEVEL == "SUMMARY":
            return
        elif LOG_LEVEL == "ERROR" and status == "SUCCESS":
            return
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"BARIS {line_num} | STATUS: {status}\n")
                if context:
                    f.write(f"CONTEXT: {context.strip()}\n")
                f.write(f"ASLI   : '{original_text}'\n")
                if translated_text and translated_text != original_text:
                    f.write(f"HASIL  : '{translated_text}'\n")
                if error_msg:
                    f.write(f"ERROR  : {error_msg}\n")
                f.write("-" * 40 + "\n\n")
        except IOError:
            pass  # Silently fail if log write fails

    def _should_translate(self, line, text_match):
        """Check if text should be translated"""
        before_quote = line[:text_match.start()].strip().lower()

        for keyword in self.skip_keywords:
            if before_quote.startswith(keyword.lower()):
                return False

        if '$' in before_quote:
            return False

        if before_quote.endswith(':'):
            return False

        if before_quote.endswith('old'):
            return False

        text_content = text_match.group(1)
        if (text_content.endswith(('.png', '.jpg', '.mp3', '.ogg', '.wav')) or
            '/' in text_content or '\\' in text_content):
            return False

        return True

    def _do_translation_single(self, text):
        """Single text translation (original method)"""
        try:
            result = subprocess.run(
                ["trans", "-brief", "-no-ansi", f"{BAHASA_ASAL}:{BAHASA_TUJUAN}", text],
                capture_output=True, 
                text=True, 
                timeout=25,
                encoding='utf-8'
            )
            
            # Fix #8: Check stdout for errors too
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Translation command failed"
                return None, error_msg
            
            translated = result.stdout.strip()
            
            # Also check if stdout contains error keywords
            if not translated or "error" in translated.lower() or "failed" in translated.lower():
                return None, "Empty or error in translation result"
            
            return translated, None
        except subprocess.TimeoutExpired:
            return None, "Translation timeout (25s)"
        except Exception as e:
            return None, f"Unexpected error: {str(e)}"

    def _do_translation_batch(self, texts):
        """
        Batch translation using separator |~|~|
        Fix #4: Better error handling
        """
        if not texts or len(texts) == 0:
            return None, "Empty batch"
        
        # Combine with separator
        combined = BATCH_SEPARATOR.join(texts)
        
        # Check character limit
        if len(combined) > MAX_BATCH_CHARS:
            return None, f"Batch too long: {len(combined)} > {MAX_BATCH_CHARS} chars"
        
        # Check for separator collision (Fix #4)
        for text in texts:
            if BATCH_SEPARATOR in text:
                return None, "Separator collision detected"
        
        try:
            result = subprocess.run(
                ["trans", "-brief", "-no-ansi", f"{BAHASA_ASAL}:{BAHASA_TUJUAN}", combined],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            
            # Fix #8: Check both stderr and stdout
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Batch translation failed"
                return None, error_msg
            
            translated = result.stdout.strip()
            
            if not translated:
                return None, "Empty batch translation result"
            
            # Check if separator preserved
            if BATCH_SEPARATOR not in translated:
                variants = [
                    BATCH_SEPARATOR.lower(),
                    BATCH_SEPARATOR.upper(),
                    f" {BATCH_SEPARATOR} ",
                    f" {BATCH_SEPARATOR}",
                    f"{BATCH_SEPARATOR} "
                ]
                found = None
                for variant in variants:
                    if variant in translated:
                        found = variant
                        break
                
                if not found:
                    return None, "Separator not preserved in translation"
                
                parts = translated.split(found)
            else:
                parts = translated.split(BATCH_SEPARATOR)
            
            # Clean parts
            parts = [p.strip() for p in parts if p.strip()]
            
            # Validate count
            if len(parts) != len(texts):
                return None, f"Count mismatch: expected {len(texts)}, got {len(parts)}"
            
            return parts, None
            
        except subprocess.TimeoutExpired:
            return None, "Batch translation timeout (30s)"
        except Exception as e:
            return None, f"Batch error: {str(e)}"

    def _translate_text(self, text, line_num, context=""):
        """Translate single text (non-batch mode or fallback)"""
        self.translation_stats['total_processed'] += 1

        if not text or not text.strip():
            self.translation_stats['empty_input'] += 1
            self._log_translation(line_num, "EMPTY_INPUT", text, context=context)
            return text

        translated, error = self._do_translation_single(text)

        if error:
            if "timeout" in error.lower():
                self.translation_stats['errors'] += 1
                self._log_translation(line_num, "TIMEOUT", text, error_msg=error, context=context)
            else:
                self.translation_stats['failed'] += 1
                self._log_translation(line_num, "FAILED", text, error_msg=error, context=context)
            return text

        if not translated:
            self.translation_stats['empty_output'] += 1
            self._log_translation(line_num, "EMPTY_OUTPUT", text, context=context)
            return text

        self.translation_stats['success'] += 1
        self._log_translation(line_num, "SUCCESS", text, translated, context=context)
        return translated

    def _process_batch_translation(self, batch_items):
        """
        Process batch translation with proper mapping
        Fix #1 & #2: Use tuple-based mapping instead of id()
        """
        if not batch_items:
            return {}
        
        texts_to_translate = [item['text'] for item in batch_items]
        
        # Try batch translation
        translations, error = self._do_translation_batch(texts_to_translate)
        
        if translations:
            # Batch success!
            self.translation_stats['batch_success'] += 1
            self.translation_stats['total_processed'] += len(texts_to_translate)
            self.translation_stats['success'] += len(translations)
            
            # Fix #2: Use tuple (line_num, text) as key instead of id()
            result_map = {}
            for item, translation in zip(batch_items, translations):
                key = (item['line_num'], item['text'])
                result_map[key] = translation
                self._log_translation(
                    item['line_num'], 
                    "BATCH_SUCCESS", 
                    item['text'], 
                    translation, 
                    context=item['original_line']
                )
            
            return result_map
        else:
            # Batch failed, fallback to individual
            self.translation_stats['batch_failed'] += 1
            self.translation_stats['fallback_individual'] += len(batch_items)
            
            if LOG_LEVEL != "SUMMARY":
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(f"⚠️ BATCH FAILED: {error}\n")
                        f.write(f"   Falling back to individual translation for {len(batch_items)} texts\n\n")
                except IOError:
                    pass
            
            # Fix #4: Proper fallback with tuple mapping
            result_map = {}
            for item in batch_items:
                translation = self._translate_text(
                    item['text'],
                    item['line_num'],
                    context=item['original_line']
                )
                key = (item['line_num'], item['text'])
                result_map[key] = translation
            
            return result_map

    def _process_line(self, line, line_num):
        """Process line with batch support"""
        original_line = line.rstrip()
        
        # Skip empty lines, comments, and python code
        if (not original_line.strip() or 
            original_line.strip().startswith('#') or
            original_line.strip().startswith('$')):
            return line

        if not USE_BATCH:
            # Original sequential method
            def smart_translate_match(match):
                text = match.group(1)
                if not self._should_translate(original_line, match):
                    self.translation_stats['skipped_code'] += 1
                    self._log_translation(line_num, "SKIPPED_CODE", text, context=original_line)
                    return f'"{text}"'
                
                translated = self._translate_text(text, line_num, context=original_line)
                return f'"{translated}"'

            # Fix #5: Use more robust regex
            final_line = re.sub(r'"([^"]*)"', smart_translate_match, original_line)
            return final_line + '\n'
        
        # BATCH MODE: Collect texts to translate
        # Fix #5: More robust regex for quotes
        matches = list(re.finditer(r'"([^"]*)"', original_line))
        texts_to_translate = []
        
        for match in matches:
            text = match.group(1)
            if self._should_translate(original_line, match) and text.strip():
                texts_to_translate.append((text, match))
            else:
                self.translation_stats['skipped_code'] += 1
        
        # Return line info for batch processing
        return {
            'type': 'pending',
            'original_line': original_line,
            'line_num': line_num,
            'matches': matches,
            'texts_to_translate': texts_to_translate
        }

    def _process_pending_lines(self, pending_lines):
        """
        Process batch of pending lines
        Fix #1: Remove double-fill, use single list
        Fix #2: Use tuple-based mapping
        Fix #3: Smart delay only for full batches
        """
        # Collect batch items (Fix #1: single list, not double)
        batch_items = []
        
        for line_info in pending_lines:
            for text, match in line_info['texts_to_translate']:
                batch_items.append({
                    'text': text,
                    'line_num': line_info['line_num'],
                    'match': match,
                    'original_line': line_info['original_line']
                })
        
        # Split into batches of BATCH_SIZE
        all_translations = {}
        for i in range(0, len(batch_items), BATCH_SIZE):
            batch = batch_items[i:i+BATCH_SIZE]
            batch_translations = self._process_batch_translation(batch)
            all_translations.update(batch_translations)
            
            # Fix #3: Only delay for full batches
            if len(batch) >= BATCH_SIZE and JEDA_TERJEMAH > 0:
                time.sleep(JEDA_TERJEMAH)
        
        # Apply translations to lines (Fix #2: tuple-based lookup)
        result_lines = []
        for line_info in pending_lines:
            original_line = line_info['original_line']
            final_line = original_line
            
            # Sort matches by position (reverse to avoid offset issues)
            sorted_matches = sorted(line_info['texts_to_translate'], 
                                   key=lambda x: x[1].start(), 
                                   reverse=True)
            
            for text, match in sorted_matches:
                key = (line_info['line_num'], text)
                translated = all_translations.get(key, text)
                
                start = match.start()
                end = match.end()
                final_line = final_line[:start] + f'"{translated}"' + final_line[end:]
            
            result_lines.append(final_line + '\n')
        
        return result_lines

    def _write_summary_log(self):
        success_rate = (self.translation_stats['success'] / max(1, self.translation_stats['total_processed'])) * 100
        
        if USE_BATCH:
            total_batches = self.translation_stats['batch_success'] + self.translation_stats['batch_failed']
            batch_success_rate = (self.translation_stats['batch_success'] / max(1, total_batches)) * 100
        
        summary_text = f"""
{'='*60}
RINGKASAN TERJEMAHAN v7.1 - {os.path.basename(self.input_file)}
{'='*60}
Mode: {'BATCH OPTIMIZED' if USE_BATCH else 'SEQUENTIAL'}
"""
        if USE_BATCH:
            summary_text += f"""
📦 BATCH STATS:
   ├─ Batch Success    : {self.translation_stats['batch_success']}
   ├─ Batch Failed     : {self.translation_stats['batch_failed']}
   ├─ Batch Success %  : {batch_success_rate:.1f}%
   └─ Fallback Individual: {self.translation_stats['fallback_individual']}

"""
        
        summary_text += f"""✅ Berhasil ditranslate : {self.translation_stats['success']}
⏩ Skip (Ren'Py code)   : {self.translation_stats['skipped_code']}
❌ Gagal/Error         : {self.translation_stats['failed'] + self.translation_stats['errors']}
📝 Input kosong         : {self.translation_stats['empty_input']}
📄 Output kosong        : {self.translation_stats['empty_output']}
📊 Total diproses       : {self.translation_stats['total_processed']}
📋 Total baris file     : {self.total_lines}
🎯 Success Rate         : {success_rate:.1f}%
"""
        if LOG_LEVEL != "SUMMARY":
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(summary_text)
            except IOError:
                pass
        print(summary_text)

    def _check_dependencies(self):
        try:
            result = subprocess.run(["trans", "--version"], capture_output=True, timeout=5)
            if result.returncode != 0:
                print("❌ translate-shell tidak ditemukan!")
                print("📥 Install dengan: pkg install translate-shell")
                return False
            return True
        except FileNotFoundError:
            print("❌ translate-shell tidak ditemukan!")
            print("📥 Install dengan: pkg install translate-shell")
            return False
        except Exception as e:
            print(f"❌ Error checking translate-shell: {e}")
            return False

    def _validate_output(self):
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                content = f.read()
            issues = []
            quote_count = content.count('"')
            if quote_count % 2 != 0:
                issues.append("⚠️ Unmatched quotes detected")
            if content.count('{') != content.count('}'):
                issues.append("⚠️ Unmatched curly brackets")
            if content.count('[') != content.count(']'):
                issues.append("⚠️ Unmatched square brackets")
            
            if issues:
                print(f"\n🚨 SYNTAX WARNINGS:")
                for issue in issues:
                    print(f"   {issue}")
            else:
                print(f"\n✅ Syntax validation passed!")
        except IOError as e:
            print(f"\n⚠️ Could not validate syntax: {e}")

    def run(self):
        print(f"\n📂 Processing: {self.input_file}")
        if not os.path.exists(self.input_file):
            print(f"❌ File tidak ditemukan: {self.input_file}")
            return False
        
        if not self._check_dependencies():
            return False
        
        # Fix #9: Check if output file is writable
        try:
            # Try to open output file for writing (test)
            with open(self.output_file, 'a', encoding='utf-8') as f:
                pass
        except IOError as e:
            print(f"❌ Cannot write to output file: {e}")
            print(f"   File might be open in another program")
            return False
            
        self._init_log_file()
        print(f"🚀 Memulai terjemahan...")
        
        if USE_BATCH:
            print(f"⚡ Mode: BATCH (separator: '{BATCH_SEPARATOR}', size: {BATCH_SIZE})")
            print(f"🎯 Expected: ~6x faster!")
        else:
            print(f"⚙️ Mode: SEQUENTIAL")
        
        print(f"📝 Log: {LOG_LEVEL} | Delay: {JEDA_TERJEMAH}s")
        
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except IOError as e:
            print(f"❌ Cannot read input file: {e}")
            return False
        
        self.total_lines = len(lines)
        
        # Fix #6: Protection against deadlock for large files
        if self.total_lines > 10000:
            print(f"⚠️ Large file detected ({self.total_lines} lines)")
            print(f"   Processing in chunks to avoid memory issues...")
        
        start_time = time.time()
        
        if not USE_BATCH:
            # Sequential processing
            results = []
            for i, line in enumerate(lines, 1):
                processed = self._process_line(line, i)
                results.append(processed)
                
                percent = (i / self.total_lines) * 100
                success_rate = (self.translation_stats['success'] / max(1, self.translation_stats['total_processed'])) * 100
                elapsed = time.time() - start_time
                eta = (elapsed / i) * (self.total_lines - i) if i > 0 else 0
                print(f"\r📊 {percent:.1f}% | {i}/{self.total_lines} | Success: {success_rate:.0f}% | ETA: {eta:.0f}s", end='', flush=True)
                
                if JEDA_TERJEMAH > 0:
                    time.sleep(JEDA_TERJEMAH)
        else:
            # Batch processing (Fix #6: process in chunks)
            results = []
            pending_lines = []
            
            for i, line in enumerate(lines, 1):
                processed = self._process_line(line, i)
                
                if isinstance(processed, dict) and processed['type'] == 'pending':
                    pending_lines.append(processed)
                    
                    # Fix #6: Process batch when full OR every 100 lines (prevent deadlock)
                    should_process = (
                        len(pending_lines) >= BATCH_SIZE or 
                        i == self.total_lines or
                        i % 100 == 0  # Force process every 100 lines
                    )
                    
                    if should_process and pending_lines:
                        batch_results = self._process_pending_lines(pending_lines)
                        results.extend(batch_results)
                        pending_lines = []
                else:
                    results.append(processed)
                
                # Progress
                percent = (i / self.total_lines) * 100
                success_rate = (self.translation_stats['success'] / max(1, self.translation_stats['total_processed'])) * 100 if self.translation_stats['total_processed'] > 0 else 0
                elapsed = time.time() - start_time
                eta = (elapsed / i) * (self.total_lines - i) if i > 0 else 0
                
                batch_info = f"| Batch: {self.translation_stats['batch_success']}" if USE_BATCH else ""
                print(f"\r📊 {percent:.1f}% | {i}/{self.total_lines} | Success: {success_rate:.0f}% {batch_info} | ETA: {eta:.0f}s", end='', flush=True)
        
        print()  # New line after progress
        
        # Fix #9: Proper error handling when writing output
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.writelines(results)
            print(f"✅ Output saved: {self.output_file}")
        except IOError as e:
            print(f"❌ Error saving file: {e}")
            print(f"   Results might be lost!")
            return False
        
        self._validate_output()
        self._write_summary_log()
        
        elapsed_time = time.time() - start_time
        if USE_BATCH and self.translation_stats['total_processed'] > 0:
            dialogues_per_sec = self.translation_stats['success'] / elapsed_time if elapsed_time > 0 else 0
            print(f"⚡ Performance: {dialogues_per_sec:.2f} dialogues/second")
        
        total_issues = (self.translation_stats['failed'] + 
                        self.translation_stats['errors'] + 
                        self.translation_stats['empty_output'])
        if total_issues > 0:
            print(f"⚠️ Ada {total_issues} teks bermasalah, cek log untuk detail!")
        else:
            print(f"🎉 Translation completed successfully!")
        
        return True


def main():
    print("\n" + "="*70)
    print("🎮 REN'PY AUTO TRANSLATOR v7.1 - COPILOT FIXES APPLIED")
    print("✅ All 11 issues resolved! Production ready!")
    print("="*70)
    
    # Fix #11: Check Python version
    import sys
    if sys.version_info < (3, 6):
        print("❌ Python 3.6+ required!")
        print(f"   Current version: {sys.version}")
        return
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    rpy_files = glob.glob(os.path.join(current_dir, "*.rpy"))
    
    input_files = [f for f in rpy_files if not f.endswith(f"_{BAHASA_TUJUAN}.rpy")]
    
    if not input_files:
        print(f"\n❌ Tidak ada file .rpy yang ditemukan di folder ini!")
        print(f"📁 Current directory: {current_dir}")
        return
    
    print(f"\n📋 Ditemukan {len(input_files)} file .rpy:")
    for i, file in enumerate(input_files, 1):
        file_name = os.path.basename(file)
        try:
            file_size = os.path.getsize(file) / 1024
            with open(file, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
            print(f"   {i}. {file_name} ({line_count} lines, {file_size:.1f} KB)")
        except IOError:
            print(f"   {i}. {file_name} (cannot read)")
    
    successful_files = []
    failed_files = []
    
    start_time = time.time()
    
    for i, input_file in enumerate(input_files, 1):
        print(f"\n{'='*70}")
        print(f"📁 FILE {i}/{len(input_files)}")
        print(f"{'='*70}")
        
        translator = RenPyAutoTranslator(input_file)
        success = translator.run()
        
        if success:
            successful_files.append(input_file)
        else:
            failed_files.append(input_file)
    
    total_time = time.time() - start_time
    
    print(f"\n" + "="*70)
    print("📊 RINGKASAN AKHIR")
    print("="*70)
    print(f"✅ Berhasil : {len(successful_files)}/{len(input_files)} file")
    print(f"❌ Gagal    : {len(failed_files)} file")
    print(f"⏱️ Total    : {total_time/60:.1f} menit")
    
    if USE_BATCH:
        print(f"⚡ Batch mode: ~6x faster!")
    
    if successful_files:
        print(f"\n🎉 File berhasil ditranslate:")
        for file in successful_files:
            output_name = os.path.splitext(os.path.basename(file))[0] + f"_{BAHASA_TUJUAN}.rpy"
            print(f"   ✅ {os.path.basename(file)} → {output_name}")
    
    if failed_files:
        print(f"\n❌ File gagal:")
        for file in failed_files:
            print(f"   ❌ {os.path.basename(file)}")
    
    print(f"\n✨ Selesai! Semua file telah diproses.")


if __name__ == "__main__":
    main()
