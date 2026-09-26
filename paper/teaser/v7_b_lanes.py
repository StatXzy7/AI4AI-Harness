"""V7 candidate B: horizontal evidence lanes with a shared illustrated control."""
from v7_common import *


def banner(ax):
    art(ax, 123, 0, 142)
    text(ax, 8, 3, f'{D["n_tasks"]} complete MATH-500 tasks', 7.5, MUTED)
    text(ax, 8, 14, '3 repeats/slot', 7.5, MUTED)
    mark(ax, 10, 33)
    text(ax, 17, 28, '8 generated + baseline', 8, TEAL, bold=True)
    text(ax, 388, 3, 'Matched executions', 7.5, MUTED, ha='right')
    text(ax, 388, 14, 'Same fixed solver', 7.5, MUTED, ha='right')
    mark(ax, 282, 33, True)
    text(ax, 289, 28, '9 identical baseline slots', 8, AMBER, bold=True)
    line(ax, 8, 45, 388, 45, '#BECBD4', .65)


def coverage(ax):
    panel_label(ax, 8, 49, 'a', 'Coverage')
    text(ax, 8, 63, 'Execution-matched oracle (%)', 7.5, MUTED)
    end = D['replay'][-1]
    text(ax, 8, 78, f'27 executions: {100*end["panel_oracle"]:.2f}% both', 8, bold=True)
    x0, x1, y0, y1 = 145, 266, 55, 77
    px = lambda x: x0+(x-3)/24*(x1-x0)
    py = lambda y: y1-(y-98.2)/.6*(y1-y0)
    for v in (98.2, 98.8):
        line(ax, x0, py(v), x1, py(v), GRID, .45)
        text(ax, x0-4, py(v), f'{v:.1f}', 7.5, MUTED, ha='right', va='center')
    line(ax, x0, y1, x1, y1, MUTED, .45)
    for v in (3, 9, 18, 27):
        line(ax, px(v), y1, px(v), y1+2, MUTED, .4)
        text(ax, px(v), 80, str(v), 7.5, MUTED, ha='center')
    xs = [px(r['executions']) for r in D['replay']]
    for key, clone in [('clone_oracle', True), ('panel_oracle', False)]:
        ax.plot(xs, [py(r[key]*100) for r in D['replay']],
                color=AMBER if clone else TEAL, lw=1,
                ls=(0,(2,1.5)) if clone else '-',
                marker='s' if clone else 'o', markersize=2.6,
                markerfacecolor='white' if clone else TEAL,
                markeredgewidth=.6, zorder=4 if clone else 3)
    text(ax, 284, 49, 'Repeat-mean headroom (pp)', 7.5, MUTED)
    for yy, key, clone in [(69, 'eval_real', False), (83, 'eval_clone', True)]:
        v = D['repeat_plugin'][key]['headroom_pp']
        c = AMBER if clone else TEAL
        mark(ax, 288, yy, clone)
        ax.add_patch(Rectangle((297,yy-3),v*24,6,facecolor=c,edgecolor='none'))
        if clone:
            ax.add_patch(Rectangle((297,yy-3),v*24,6,facecolor='none',
                                  edgecolor='white',lw=0,hatch='////'))
        text(ax,388,yy,f'{v:.2f}',9,c,bold=True,ha='right',va='center')
    line(ax,297,62,297,88,MUTED,.45)
    line(ax, 8, 94, 388, 94, RULE, .55)


def repeatability(ax):
    panel_label(ax, 8, 99, 'b', 'Repeatability')
    text(ax, 8, 114, 'Residual r · 95% CI', 7.5, MUTED)
    px = lambda x: 149+(x+.1)/1.1*103
    for v in (0,.5,1):
        line(ax,px(v),104,px(v),131,GRID,.45)
        text(ax,px(v),133,f'{v:g}',7.5,MUTED,ha='center')
    for key, yy, clone in [('eval_real',109,False),('eval_clone',126,True)]:
        s = D['repeatability'][key]
        v = s['mean_pearson_residualized']
        lo,hi = s['mean_pearson_residualized_ci95']
        c = AMBER if clone else TEAL
        line(ax,px(lo),yy,px(hi),yy,c,1.3)
        for q in (lo,hi):
            line(ax,px(q),yy-2.5,px(q),yy+2.5,c,.75)
        mark(ax,px(v),yy,clone,4)
        text(ax,136,yy,f'{v:.3f}',8.5,c,bold=True,ha='right',va='center')
    text(ax,270,99,'Persistent scores vs baseline',7.5,MUTED)
    text(ax,270,110,'Tasks · any member · 3/3 repeats',7.5,MUTED)
    s = D['repeatability']['eval_real']['all_repeat_patterns']
    for i in range(s['loss_tasks']):
        ax.add_patch(Rectangle((270+(i%20)*2.2,121+(i//20)*1.85),1.4,1.25,
                               facecolor=LOSS,edgecolor='none'))
    text(ax,320,121,f'{s["loss_tasks"]} losses',8,LOSS,bold=True)
    ax.add_patch(Rectangle((270,137),1.65,1.65,facecolor=TEAL,edgecolor='none'))
    text(ax,275,132,f'{s["win_tasks"]} win*',7.5,TEAL,bold=True)
    text(ax,307,132,'*Extraction-sensitive',7.5,MUTED)
    line(ax,8,142,388,142,RULE,.55)


def selection(ax):
    panel_label(ax,8,146,'c','Useful selection')
    text(ax,8,159,'2 repeats: freeze choices',7.5,MUTED)
    text(ax,8,171,'per-task + best fixed',7.5,MUTED)
    arrow(ax,(11,188),(23,188),BLUE)
    text(ax,27,183,'Test third · rotate 3 folds',7.5,BLUE)
    text(ax,145,146,'Clone-adjusted held-out gain (pp)',7.5,MUTED)
    s = D['primary']['paired_difference']
    v=s['D_real_minus_clone']*100
    lo,hi=[q*100 for q in s['D_ci95']]
    text(ax,211,158,f'{v:+.2f}; 95% CI [{lo:+.2f}, {hi:+.2f}]'.replace('-','−'),
         7.5,BLUE,bold=True,ha='center')
    px=lambda v: 153+(v+2)/4*113
    line(ax,px(0),166,px(0),178,'#93A2AE',.6,ls=(0,(2,2)))
    line(ax,px(-2),174,px(2),174,MUTED,.45)
    for q in (-2,0,2):
        line(ax,px(q),174,px(q),176,MUTED,.4)
        text(ax,px(q),176,str(q).replace('-','−'),7.5,MUTED,ha='center')
    line(ax,px(lo),170,px(hi),170,BLUE,1.3)
    for q in (lo,hi):
        line(ax,px(q),167.5,px(q),172.5,BLUE,.75)
    ax.plot(px(v),170,marker='D',color=BLUE,markersize=4,
            markeredgecolor='white',markeredgewidth=.4,zorder=6)
    text(ax,211,187,'Specialization unresolved',7.5,bold=True,ha='center')
    box(ax,284,149,104,45,BPALE,edge='none',radius=2)
    text(ax,290,152,'Frozen feature selector',8,bold=True)
    text(ax,290,165,'Baseline',8,BLUE,bold=True)
    p=D['selector']
    text(ax,290,177,f'{p["choices_on_subset"]["bare"]}/{D["n_tasks"]} tasks',7.5,MUTED)
    text(ax,382,165,f'{p["gain_vs_bare_pp"]:.2f}',10,BLUE,bold=True,ha='right')
    text(ax,382,179,'pp gain',7.5,MUTED,ha='right')


def draw():
    with plt.rc_context(STYLE):
        fig,ax=canvas()
        banner(ax)
        coverage(ax)
        repeatability(ax)
        selection(ax)
        return fig


if __name__=='__main__':
    import fitz
    fig=draw()
    with plt.rc_context(STYLE):
        fig.savefig('/tmp/v7_b_lanes.pdf')
    plt.close(fig)
    with fitz.open('/tmp/v7_b_lanes.pdf') as doc:
        doc[0].get_pixmap(matrix=fitz.Matrix(4,4),alpha=False).save('/tmp/v7_b_lanes.png')
        print(doc[0].get_text())
