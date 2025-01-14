from django.shortcuts import render, redirect
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.core.paginator import Paginator
from .models import (
    Explain,
    Team,
    SubmitResult,
    LeaderTime,
    Config
)

import markdown
import pandas
import os
import io
from sklearn.metrics import f1_score


def page_index(request):
    index_cont = Explain.objects.get(explain_id='index_cont').explain_text
    index_data = Explain.objects.get(explain_id='index_data').explain_text
    index_cont = markdown.markdown(index_cont)
    index_data = markdown.markdown(index_data)
    return render(request, 'index.html', {
        'index_cont': index_cont,
        'index_data': index_data
    })

def page_login(request):
    if request.user.is_anonymous:
        if 'message' in request.session:
            msg = request.session['message']
            del request.session['message']
            return render(request, 'login.html', {'message': msg})
        return render(request, 'login.html')
    else:
        return redirect('index')

def page_logout(request):
    if request.user.is_anonymous:
        return redirect('login')
    logout(request)
    return redirect('login')

def page_leader(request):
    if request.user.is_anonymous:
        return redirect('login')
    else:
        leaderboard = SubmitResult.objects.filter(submit_leader=True).order_by('-submit_score', 'submit_create')

        leaderboard_page = Paginator(leaderboard, 15)
        now_page = request.GET.get('page')
        if now_page is None:
            now_page = 1
        else:
            now_page = int(now_page)

        if now_page > leaderboard_page.num_pages:
            now_page = leaderboard_page.num_pages
        elif now_page < 1:
            now_page = 1

        team_submit = []
        for l in leaderboard_page.get_page(now_page):
            team_instance = l.submit_team_pk
            leader_time_instance = team_instance.leader_team
            create_time = leader_time_instance.leader_create
            create_time = f'{create_time.day}일 {create_time.hour}시 {create_time.minute}분 {create_time.second}초'
            team_submit.append({
                'team_name': team_instance.team_name,
                'score': l.submit_score,
                'create_time': create_time,
                'count': leader_time_instance.leader_count,
            })
        context = {
            'submit_log': team_submit,
            'total_page': leaderboard_page.num_pages,
            'now_page': now_page
        }
        return render(request, 'leader.html', context)

def page_submit(request):
    if request.user.is_anonymous:
        return redirect('login')
    else:
        team_instance = request.user.team_user.all()
        least_leader_time_sec = int(Config.objects.get(config_name='REG_LEADERBOARD_SEC').config_value)
        if team_instance:
            team_instance = team_instance[0]
            team_users = []
            for u in team_instance.team_member.all():
                name = u.get_full_name()
                last_submit = u.submit_user.all().order_by('-submit_create')
                if last_submit:
                    last_submit = last_submit[0].submit_create
                    last_submit = f'{last_submit.day}일 {last_submit.hour}시 {last_submit.minute}분 {last_submit.second}초'
                else:
                    last_submit = None
                team_users.append({'name': name, 'last_submit': last_submit})

            team_sub_log = SubmitResult.objects.filter(submit_team_pk=request.user.team_user.all()[0])
            team_sub_log = team_sub_log.order_by('-submit_score')

            team_log_page = Paginator(team_sub_log, 10)
            now_page = request.GET.get('page')
            if now_page is None:
                now_page = 1
            else:
                now_page = int(now_page)

            if now_page > team_log_page.num_pages:
                now_page = team_log_page.num_pages
            elif now_page < 1:
                now_page = 1

            team_submit = []
            for l in team_log_page.get_page(now_page):
                create_time = l.submit_create
                create_time = f'{create_time.day}일 {create_time.hour}시 {create_time.minute}분 {create_time.second}초'
                team_submit.append({
                    'sub_num': l.submit_pk,
                    'file_name': l.submit_name,
                    'submitter': l.submit_user_pk.get_full_name(),
                    'score': l.submit_score,
                    'create_time': create_time,
                    'is_selected': bool(l.submit_leader),
                })

            context = {
                'team_users': team_users,
                'submit_log': team_submit,
                'total_page': team_log_page.num_pages,
                'now_page': now_page
            }

            last_submit = LeaderTime.objects.filter(leader_team=team_instance)
            context['last_leader'] = f'리더보드 등록이 가능합니다.'
            if last_submit:
                diff = now() - last_submit[0].leader_create
                if diff.seconds < least_leader_time_sec:
                    context['last_leader'] = f'리더보드 등록은 팀당 {least_leader_time_sec // 60}분에 한번만 가능합니다. ' \
                                             f'현재 {(least_leader_time_sec - diff.seconds) // 60}분 ' \
                                             f'{(least_leader_time_sec - diff.seconds) % 60}초 남았습니다.'


            if 'message' in request.session:
                context['message'] = request.session['message']
                del request.session['message']

            return render(request, 'submit.html', context)
        else:
            request.session['message'] = '팀에 소속되지 않은 사용자입니다.'
            return redirect('login')

def page_change_password(request):
    if request.user.is_anonymous:
        return redirect('login')
    else:
        if 'message' in request.session:
            msg = request.session['message']
            del request.session['message']
            return render(request, 'password.html', {'message': msg})
        return render(request, 'password.html')

def form_change_password(request):
    if request.user.is_anonymous:
        return redirect('login')
    else:
        if request.method == 'POST':
            text_password = request.POST['text_password']
            user = request.user
            if check_password(text_password, user.password):
                new_password = request.POST['new_password']
                new_password_check = request.POST['new_password_check']
                if new_password_check == new_password:
                    try:
                        validator = MinimumLengthValidator(min_length=6)
                        validator.validate(new_password)
                    except:
                        request.session['message'] = '비밀번호는 6자리 이상이어야 합니다.'
                        return redirect('password_change')
                    user.set_password(new_password)
                    user.save()
                    return redirect('index')
                else:
                    request.session['message'] = '재입력한 비밀번호가 다릅니다.'
                    return redirect('password_change')
            else:
                request.session['message'] = '기존 비밀번호가 틀립니다.'
                return redirect('password_change')
        else:
            request.session['message'] = 'request error.'
            return redirect('password_change')

def form_submission(request):
    if request.user.is_anonymous:
        return redirect('login')
    elif request.method == 'POST' and request.FILES['file_data']:
        file = request.FILES['file_data']
        real_name = file.name
        change_name = get_random_string(20)
        while os.path.exists(f'./media/submits/{change_name}'):
            change_name = get_random_string(20)
        file.name = change_name

        try:
            answer = pandas.read_csv('./static/new_weather_data_test_y.csv', index_col=0)
            submission = pandas.read_csv(io.StringIO(request.FILES['file_data'].read().decode('utf-8')), index_col=0)
            assert answer.shape == submission.shape

            answer = answer['weather'].values
            submission = submission['weather'].values
            submit_score = f1_score(answer, submission, average='weighted')
            # submit_score = sum(answer == submission) / len(answer) * 100
        except:
            request.session['message'] = '파일 제출 과정에서 오류가 발생했거나 형식이 다릅니다.'
            return redirect('submit')

        sub = SubmitResult(
            submit_file=request.FILES['file_data'],
            submit_team_pk=request.user.team_user.all()[0],
            submit_name=real_name,
            submit_user_pk=request.user,
            submit_score=submit_score
        )
        sub.save()
        return redirect('submit')
    else:
        request.session['message'] = '파일 제출 과정에서 오류가 발생했습니다.'
        return redirect('submit')

def form_leader(request):
    if request.user.is_anonymous:
        return redirect('login')
    elif request.method == 'GET' and request.GET['sub_pk']:
        least_leader_time_sec = int(Config.objects.get(config_name='REG_LEADERBOARD_SEC').config_value)
        team_instance = request.user.team_user.all()[0]
        last_submit = LeaderTime.objects.filter(leader_team=team_instance)
        if last_submit:
            last_submit = last_submit[0]
            diff = now() - last_submit.leader_create
            if diff.seconds < least_leader_time_sec:
                request.session['message'] = f'리더보드 등록은 팀당 {least_leader_time_sec // 60}분 {least_leader_time_sec % 60}초에 한번만 가능합니다. ' \
                                             f'현재 {(least_leader_time_sec - diff.seconds) // 60}분 {(least_leader_time_sec - diff.seconds) % 60}초 남았습니다.'
                return redirect('submit')
        else:
            last_submit = LeaderTime(leader_team=team_instance, leader_count=0)
            last_submit.save()
        sub_pk = request.GET['sub_pk']
        target_sub = SubmitResult.objects.filter(submit_pk=sub_pk)
        if target_sub:
            team_sub_log = SubmitResult.objects.filter(submit_team_pk=request.user.team_user.all()[0])
            for t in team_sub_log:
                t.submit_leader = False
                t.save()
            target_sub[0].submit_leader = True
            target_sub[0].save()

            last_submit.leader_count += 1
            last_submit.save()

            return redirect('submit')
        else:
            request.session['message'] = '리더보드 등록 과정에서 오류가 발생했습니다.'
            return redirect('submit')
    else:
        request.session['message'] = '리더보드 등록 과정에서 오류가 발생했습니다.'
        return redirect('submit')

def form_login(request):
    if request.method == 'POST':
        id = request.POST['text_id']
        password = request.POST['text_password']
        user = authenticate(request, username=id, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        else:
            request.session['message'] = '유저가 존재하지 않거나 패스워드가 틀렸습니다.'
            return redirect('login')
    else:
        request.session['message'] = 'request error.'
        return redirect('login')
