import pygame
import sys
import random
import numpy as np
import threading
import time

pygame.init()
# Initialize mixer with specific buffer to reduce audio lag
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

# ============== AC TETRIS CONFIG ==============
WIDTH, HEIGHT = 600, 400
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("AC TETRIS – 90s Handheld Glory ♡")
clock = pygame.time.Clock()
FONT = pygame.font.SysFont("consolas", 28, bold=True)
SMALL_FONT = pygame.font.SysFont("consolas", 18)

BLACK = (0, 0, 0)
NEON_GREEN = (0, 255, 0)
NEON_PINK = (255, 20, 147)

BLOCK_SIZE = 20
GRID_W, GRID_H = 10, 20
PLAY_X = (WIDTH - GRID_W * BLOCK_SIZE) // 2 - 60
PLAY_Y = (HEIGHT - GRID_H * BLOCK_SIZE) // 2 - 20

SHAPES = [
    [[1,1,1,1]],          # I
    [[1,1],[1,1]],        # O
    [[0,1,0],[1,1,1]],    # T
    [[1,0,0],[1,1,1]],    # J
    [[0,0,1],[1,1,1]],    # L
    [[0,1,1],[1,1,0]],    # S
    [[1,1,0],[0,1,1]]     # Z
]
COLORS = [(0,255,255),(255,255,0),(128,0,128),(0,0,255),(255,165,0),(0,255,0),(255,0,0)]

# ============== CLASSES ==============

class Piece:
    def __init__(self, x, y, shape_idx):
        self.x = x
        self.y = y
        self.shape_idx = shape_idx
        self.rotation = 0
        self.color = COLORS[shape_idx]

    def get_shape(self):
        shape = SHAPES[self.shape_idx]
        rotated_shape = shape
        for _ in range(self.rotation):
            rotated_shape = [list(row) for row in zip(*rotated_shape[::-1])]
        return rotated_shape

class Tone(pygame.mixer.Sound):
    def __init__(self, frequency, duration=0.1, volume=0.15):
        sample_rate = 44100
        frames = int(duration * sample_rate)
        if frequency == 0: frequency = 1  # Avoid division by zero
        period = int(sample_rate / frequency)
        # Create a square wave
        arr = np.array([32767 if (i % period) < (period//2) else -32767 for i in range(frames)], dtype=np.int16)
        super().__init__(arr)
        self.set_volume(volume)

# ============== GLOBAL STATE & FUNCTIONS ==============

music_playing = False
grid = [[(0,0,0) for _ in range(GRID_W)] for _ in range(GRID_H)]
current_piece = None
next_piece = None
held_piece = None
can_hold = True
score = 0
level = 1
lines_cleared_total = 0
last_clear_was_tetris = False
flash_timer = 0
game_state = "MENU" # Start at menu
pause = False

def new_piece():
    return Piece(GRID_W//2 - 2, 0, random.randint(0,6))

def valid_move(piece, dx=0, dy=0, new_rot=None):
    old_rot = piece.rotation
    if new_rot is not None:
        piece.rotation = new_rot
    
    shape = piece.get_shape()
    valid = True
    for y, row in enumerate(shape):
        for x, cell in enumerate(row):
            if cell:
                gx = piece.x + x + dx
                gy = piece.y + y + dy
                # Check boundaries and collision
                if gx < 0 or gx >= GRID_W or gy >= GRID_H or (gy >= 0 and grid[gy][gx] != (0,0,0)):
                    valid = False
                    break
        if not valid: break
    
    # Restore rotation if we were just testing
    if new_rot is not None and not valid:
        piece.rotation = old_rot
    elif new_rot is not None and valid:
        piece.rotation = old_rot 
        
    return valid

def lock_piece():
    global last_clear_was_tetris, flash_timer
    shape = current_piece.get_shape()
    for y, row in enumerate(shape):
        for x, cell in enumerate(row):
            if cell:
                gx = current_piece.x + x
                gy = current_piece.y + y
                if gy >= 0:
                    grid[gy][gx] = current_piece.color
    clear_lines()

def clear_lines():
    global score, lines_cleared_total, last_clear_was_tetris, level
    
    # Identify lines to clear
    new_grid = [row for row in grid if any(cell == (0,0,0) for cell in row)]
    lines_cleared = GRID_H - len(new_grid)
    
    # Add new empty lines at top
    for _ in range(lines_cleared):
        new_grid.insert(0, [(0,0,0)]*GRID_W)
    
    # Update grid in place
    grid[:] = new_grid

    if lines_cleared > 0:
        points = [0, 100, 300, 500, 800][lines_cleared]
        if last_clear_was_tetris and lines_cleared == 4:
            points *= 2
        score += points * level
        lines_cleared_total += lines_cleared
        if lines_cleared_total // 10 + 1 > level:
            level += 1
        
        last_clear_was_tetris = (lines_cleared == 4)
        if last_clear_was_tetris:
            flash_timer = 10
        
        # T-Spin detection (very basic)
        if current_piece.shape_idx == 2: # T-piece
            score += 100

def draw_grid():
    for y in range(GRID_H):
        for x in range(GRID_W):
            color = grid[y][x]
            rect = (PLAY_X + x*BLOCK_SIZE, PLAY_Y + y*BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
            if color != (0,0,0):
                pygame.draw.rect(screen, color, rect)
                pygame.draw.rect(screen, BLACK, rect, 1) # inner border
            pygame.draw.rect(screen, (30,30,30), rect, 1) # grid lines

def draw_piece(piece, offset_x=0, offset_y=0):
    shape = piece.get_shape()
    for y, row in enumerate(shape):
        for x, cell in enumerate(row):
            if cell:
                pygame.draw.rect(screen, piece.color,
                    (PLAY_X + (piece.x + x + offset_x)*BLOCK_SIZE,
                     PLAY_Y + (piece.y + y + offset_y)*BLOCK_SIZE,
                     BLOCK_SIZE, BLOCK_SIZE))
                pygame.draw.rect(screen, BLACK, 
                    (PLAY_X + (piece.x + x + offset_x)*BLOCK_SIZE,
                     PLAY_Y + (piece.y + y + offset_y)*BLOCK_SIZE,
                     BLOCK_SIZE, BLOCK_SIZE), 1)

def draw_next_hold():
    # Draw Next
    next_label = SMALL_FONT.render("NEXT", True, NEON_GREEN)
    screen.blit(next_label, (WIDTH - 150, 50))
    if next_piece:
        shape = next_piece.get_shape()
        # Center the piece visually in the box
        offset_y = 1 if len(shape) < 3 else 0
        offset_x = 1 if len(shape[0]) < 3 else 0
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    pygame.draw.rect(screen, next_piece.color,
                        (WIDTH - 150 + (x+offset_x)*BLOCK_SIZE, 80 + (y+offset_y)*BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE))

    # Draw Hold
    hold_label = SMALL_FONT.render("HOLD", True, NEON_GREEN)
    screen.blit(hold_label, (50, 50))
    if held_piece:
        shape = held_piece.get_shape()
        offset_y = 1 if len(shape) < 3 else 0
        offset_x = 1 if len(shape[0]) < 3 else 0
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    pygame.draw.rect(screen, held_piece.color,
                        (50 + (x+offset_x)*BLOCK_SIZE, 80 + (y+offset_y)*BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE))

def reset_game():
    global grid, current_piece, next_piece, held_piece, can_hold, score, level, lines_cleared_total, last_clear_was_tetris, pause, music_playing
    grid = [[(0,0,0) for _ in range(GRID_W)] for _ in range(GRID_H)]
    current_piece = new_piece()
    next_piece = new_piece()
    held_piece = None
    can_hold = True
    score = 0
    level = 1
    lines_cleared_total = 0
    last_clear_was_tetris = False
    pause = False
    music_playing = True

# ============== AUDIO ==============

MELODY = [
    (659, 0.4), (494, 0.2), (523, 0.2), (587, 0.4), (523, 0.2), (494, 0.2), 
    (440, 0.4), (440, 0.2), (523, 0.2), (659, 0.4), (587, 0.2), (523, 0.2), 
    (494, 0.4), (523, 0.2), (587, 0.4), (659, 0.4), (523, 0.2), (440, 0.4), (440, 0.6)
]

def play_melody():
    global music_playing
    while True:
        if not music_playing:
            time.sleep(0.1)
            continue
        
        for freq, dur in MELODY:
            if not music_playing: break
            # Speed up music slightly as levels increase (cap at level 10 speed)
            speed_mult = max(0.5, 1.0 - (level * 0.05))
            
            try:
                tone = Tone(freq, dur * speed_mult)
                tone.play()
                time.sleep(dur * speed_mult * 1.1)
            except:
                pass # safely ignore mixer errors
        time.sleep(0.5)

melody_thread = threading.Thread(target=play_melody, daemon=True)
melody_thread.start()

# ============== MAIN LOOP ==============

# Initialize variables properly now that functions are defined
reset_game()
music_playing = False # Start music off for menu
game_state = "MENU"   # Ensure we start in menu

selected = 0
menu_options = ["PLAY GAME", "HOW TO PLAY", "CREDITS", "ABOUT", "EXIT GAME"]
drop_speed = 0.5
last_drop = time.time()
running = True

while running:
    screen.fill(BLACK)
    current_time = time.time()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            
        if event.type == pygame.KEYDOWN:
            if game_state == "MENU":
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(menu_options)
                if event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(menu_options)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if menu_options[selected] == "PLAY GAME":
                        game_state = "PLAYING"
                        reset_game()
                    elif menu_options[selected] == "HOW TO PLAY":
                        game_state = "HOWTO"
                    elif menu_options[selected] == "CREDITS":
                        game_state = "CREDITS"
                    elif menu_options[selected] == "ABOUT":
                        game_state = "ABOUT"
                    elif menu_options[selected] == "EXIT GAME":
                        running = False
                if event.key == pygame.K_ESCAPE:
                    running = False
                    
            elif game_state == "PLAYING":
                if not pause:
                    if event.key == pygame.K_LEFT:
                        if valid_move(current_piece, dx=-1):
                            current_piece.x -= 1
                    if event.key == pygame.K_RIGHT:
                        if valid_move(current_piece, dx=1):
                            current_piece.x += 1
                    if event.key == pygame.K_DOWN:
                        if valid_move(current_piece, dy=1):
                            current_piece.y += 1
                            score += 1
                    if event.key == pygame.K_UP:
                        # Clockwise
                        if valid_move(current_piece, new_rot=(current_piece.rotation + 1) % 4):
                            current_piece.rotation = (current_piece.rotation + 1) % 4
                    if event.key == pygame.K_z:
                        # Counter-clockwise
                        if valid_move(current_piece, new_rot=(current_piece.rotation - 1) % 4):
                            current_piece.rotation = (current_piece.rotation - 1) % 4
                    if event.key == pygame.K_SPACE:
                        if can_hold:
                            if held_piece is None:
                                held_piece = current_piece
                                current_piece = next_piece
                                next_piece = new_piece()
                            else:
                                held_piece, current_piece = current_piece, held_piece
                            
                            # Reset position of piece pulled from hold
                            current_piece.x = GRID_W//2 - 2
                            current_piece.y = 0
                            current_piece.rotation = 0
                            can_hold = False
                    if event.key == pygame.K_p:
                        pause = not pause
                        
                if event.key == pygame.K_ESCAPE:
                    game_state = "MENU"
                    music_playing = False
                    pause = False
            
            elif game_state in ("HOWTO", "ABOUT", "CREDITS", "GAMEOVER"):
                if event.key == pygame.K_ESCAPE:
                    game_state = "MENU"
                    music_playing = False

    # --- UPDATE & DRAW ---

    if game_state == "MENU":
        title = FONT.render("AC TETRIS", True, NEON_GREEN)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 60))
        for i, opt in enumerate(menu_options):
            color = NEON_PINK if i == selected else NEON_GREEN
            txt = SMALL_FONT.render(opt, True, color)
            screen.blit(txt, (WIDTH//2 - txt.get_width()//2, 140 + i*40))
        
        hint = SMALL_FONT.render("Arrows to Select, Enter to Choose", True, (100,100,100))
        screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT - 30))

    elif game_state == "PLAYING":
        if not pause:
            # Gravity
            actual_speed = max(0.05, drop_speed - (level * 0.04))
            if current_time - last_drop > actual_speed:
                last_drop = current_time
                if valid_move(current_piece, dy=1):
                    current_piece.y += 1
                else:
                    lock_piece()
                    current_piece = next_piece
                    next_piece = new_piece()
                    can_hold = True
                    if not valid_move(current_piece):
                        game_state = "GAMEOVER"
                        music_playing = False

        draw_grid()
        if current_piece:
            draw_piece(current_piece) # Ghost piece could be added here
        draw_next_hold()

        score_txt = SMALL_FONT.render(f"SCORE {score}", True, NEON_GREEN)
        level_txt = SMALL_FONT.render(f"LEVEL {level}", True, NEON_GREEN)
        screen.blit(score_txt, (20, 20))
        screen.blit(level_txt, (20, 50))

        if flash_timer > 0:
            flash_timer -= 1
            pygame.draw.rect(screen, NEON_PINK, (0,0,WIDTH,HEIGHT), 8)

        if pause:
            pause_txt = FONT.render("PAUSED – press P", True, NEON_PINK)
            screen.blit(pause_txt, (WIDTH//2 - pause_txt.get_width()//2, HEIGHT//2))

    elif game_state == "GAMEOVER":
        draw_grid() # Show the final state
        overlay = pygame.Surface((WIDTH, HEIGHT))
        overlay.set_alpha(180)
        overlay.fill(BLACK)
        screen.blit(overlay, (0,0))
        
        txt = FONT.render("GAME OVER", True, NEON_PINK)
        score_final = SMALL_FONT.render(f"Final Score: {score}", True, NEON_GREEN)
        retry_txt = SMALL_FONT.render("Press ESC for Menu", True, (255,255,255))
        
        screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 40))
        screen.blit(score_final, (WIDTH//2 - score_final.get_width()//2, HEIGHT//2 + 10))
        screen.blit(retry_txt, (WIDTH//2 - retry_txt.get_width()//2, HEIGHT//2 + 50))
        
    elif game_state == "HOWTO":
        header = FONT.render("HOW TO PLAY", True, NEON_PINK)
        screen.blit(header, (WIDTH//2 - header.get_width()//2, 40))
        
        lines = [
            "Arrow Keys : Move & Rotate",
            "Space      : Hold Piece",
            "Z Key      : Counter-Rotate",
            "P Key      : Pause Game",
            "ESC        : Return to Menu"
        ]
        y_off = 120
        for line in lines:
            t = SMALL_FONT.render(line, True, NEON_GREEN)
            screen.blit(t, (WIDTH//2 - t.get_width()//2, y_off))
            y_off += 40
            
    elif game_state == "ABOUT":
        header = FONT.render("ABOUT AC TETRIS", True, NEON_PINK)
        screen.blit(header, (WIDTH//2 - header.get_width()//2, 40))
        
        lines = [
            "A neon-soaked tribute to the",
            "classic 90s handheld puzzle games.",
            "",
            "Built entirely in Python using",
            "Pygame Community Edition.",
            "",
            "Procedural Audio Engine Included."
        ]
        y_off = 120
        for line in lines:
            t = SMALL_FONT.render(line, True, NEON_GREEN)
            screen.blit(t, (WIDTH//2 - t.get_width()//2, y_off))
            y_off += 30

    elif game_state == "CREDITS":
        header = FONT.render("CREDITS", True, NEON_PINK)
        screen.blit(header, (WIDTH//2 - header.get_width()//2, 40))
        
        lines = [
            "Programming  : AC",
            "Visual Style : Retro Neon",
            "Audio Design : Numpy Wave Gen",
            "Framework    : Pygame",
            "",
            "Dedicated to the Arcade Legends"
        ]
        y_off = 120
        for line in lines:
            t = SMALL_FONT.render(line, True, NEON_GREEN)
            screen.blit(t, (WIDTH//2 - t.get_width()//2, y_off))
            y_off += 35

    if game_state in ("HOWTO", "ABOUT", "CREDITS"):
        footer = SMALL_FONT.render("Press ESC to Return", True, (150,150,150))
        screen.blit(footer, (WIDTH//2 - footer.get_width()//2, HEIGHT - 40))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
